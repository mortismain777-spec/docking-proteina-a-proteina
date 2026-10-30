"""Pruebas sin enviar estructuras al servidor; ejecutar python -m unittest -v."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from data_fetcher import StructureFetcher, sha256, validate_pdb
from job_runner import BatchRunner, LOG_FIELDS, accepted, read_log
from pipeline import Pipeline, protein_key, read_inputs
from results_parser import best_score, export

PDB = "ATOM      1  CA  ALA A   1      12.000  13.000  14.000  1.00 90.00           C  \nEND\n"
INPUT = "tipo,identificador,nombre_comun,categoria\nRBP,P09651,RBP1,\nreceptor,P00533,EGFR,A\n"
HTML = "<table><tr><th>Rank</th><th>Docking <b>Score</b></th><th>Confidence Score</th></tr><tr><td>1</td><td>-120.5</td><td>99</td></tr><tr><td>2</td><td>-180.25</td><td>10</td></tr></table>"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def pdb(self):
        path = self.root / "local.pdb"
        path.write_text(PDB)
        return path

    def pipeline(self, dummy=False):
        return Pipeline.create(self.root / "run", read_inputs(INPUT), 9606, {}, dummy, "")

    def test_input_dedup_and_conflict(self):
        self.assertEqual(len(read_inputs(INPUT + "RBP,P09651,RBP1,\n")), 2)
        with self.assertRaises(ValueError):
            read_inputs(INPUT + "receptor,P00533,EGFR,B\n")

    def test_gene_resolution_rejects_ambiguity(self):
        client = Mock()
        client.get.return_value.json.return_value = {"results": [{"primaryAccession": "P1"}, {"primaryAccession": "P2"}]}
        with self.assertRaises(ValueError):
            StructureFetcher(self.root, client=client).resolve("EGFR")
        self.assertIn("organism_id:9606", client.get.call_args.kwargs["params"]["query"])

    def test_local_pdb_and_checksum(self):
        result = StructureFetcher(self.root / "structures").fetch("UNKNOWN", str(self.pdb()))
        self.assertEqual(result["sha256"], sha256(self.pdb()))
        invalid = self.root / "invalid.pdb"
        invalid.write_text("<html>error</html>")
        with self.assertRaises(ValueError):
            validate_pdb(invalid)

    def test_alphafold_download_and_multiple_models(self):
        client = Mock()
        response = Mock()
        response.json.return_value = [{"pdbUrl": "https://alphafold.ebi.ac.uk/files/model.pdb"}]
        download = Mock(content=PDB.encode())
        client.get.side_effect = [response, download]
        result = StructureFetcher(self.root / "structures", client=client).fetch("P00533")
        self.assertTrue(Path(result["path"]).exists())
        response.json.return_value = [{"pdbUrl": "a"}, {"pdbUrl": "b"}]
        client.get.side_effect = [response]
        with self.assertRaises(ValueError):
            StructureFetcher(self.root / "other", client=client).fetch("P00533")

    def test_full_matrix_controls_and_resume_identity(self):
        pipeline = self.pipeline(dummy=True)
        path = self.pdb()
        def fake_fetch(identifier, local=None):
            return {"path": str(path), "sha256": sha256(path), "source": "fixture", "uniprot": identifier}
        with patch("pipeline.StructureFetcher.fetch", side_effect=fake_fetch), patch("pipeline.StructureFetcher.fetch_pdb", side_effect=fake_fetch):
            pipeline.prepare()
        self.assertEqual(len(pipeline.config["jobs"]), 3)
        self.assertEqual(sum(j["Categoria_Receptor"] == "control" for j in pipeline.config["jobs"]), 2)
        restored = Pipeline.load(pipeline.directory)
        restored.prepare()
        self.assertEqual(restored.config["jobs"], pipeline.config["jobs"])

    def test_missing_structure_does_not_abort(self):
        pipeline = self.pipeline()
        path = self.pdb()
        def fetch(identifier, local=None):
            if identifier == "P00533":
                raise RuntimeError("404")
            return {"path": str(path), "sha256": sha256(path), "source": "fixture"}
        with patch("pipeline.StructureFetcher.fetch", side_effect=fetch):
            pipeline.prepare()
        self.assertEqual(len(pipeline.config["jobs"]), 1)
        self.assertEqual(len(pipeline.config["skipped_pairs"]), 1)
        self.assertIn("receptor:P00533", pipeline.config["errors"])

    def test_score_header_is_required_and_nonfinite_ignored(self):
        self.assertEqual(best_score(HTML), -180.25)
        self.assertIsNone(best_score("<p>Running -999</p>"))
        self.assertIsNone(best_score(HTML.replace("Docking <b>Score</b>", "Confidence Score")))
        self.assertIsNone(best_score("<table><tr><th>Docking Score</th></tr><tr><td>NaN</td></tr></table>"))

    def test_export_sort_and_formula_safety(self):
        import pandas as pd
        from openpyxl import load_workbook
        from results_parser import COLUMNS, summary
        jobs = [{"jobname": name, "RBP": "=1+1", "Receptor": name, "Categoria_Receptor": "control"} for name in ("one", "two", "pending")]
        log = self.root / "run-log.csv"
        with log.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
            writer.writeheader()
            for name in ("one", "two"):
                writer.writerow({"jobname": name, "token": name, "ok": True, "result_url": f"http://hdock.phys.hust.edu.cn/data/{name}"})
        frame = summary(jobs, log, {"one": {"token": "one", "score": -1, "state": "completado"}, "two": {"token": "two", "score": -100, "state": "completado"}})
        self.assertEqual(list(frame["Receptor"]), ["two", "one", "pending"])
        self.assertTrue(pd.isna(frame.iloc[-1]["Docking_Score"]))
        _, workbook_path = export(frame, self.root / "results")
        workbook = load_workbook(workbook_path)
        sheet = workbook.active
        self.assertEqual(sheet["A2"].value, "'=1+1")
        self.assertEqual(sheet["D2"].value, -100)
        self.assertIsNone(sheet["D4"].value)
        self.assertEqual(sheet.freeze_panes, "D2")
        self.assertEqual(list(frame.columns), COLUMNS)

    def test_real_subprocess_adapter_skips_accepted_jobs(self):
        script = self.root / "fake_batch.py"
        script.write_text('''import argparse,csv,pathlib
p=argparse.ArgumentParser();p.add_argument('csv');p.add_argument('--out');p.add_argument('-j');a=p.parse_args()
job=next(csv.DictReader(open(a.csv,encoding='utf-8')))
with open(pathlib.Path(a.out)/'run-log.csv','w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['jobname','token','result_url','ok','error']);w.writeheader();w.writerow(dict(jobname=job['jobname'],token='testtoken123',result_url='http://hdock.phys.hust.edu.cn/data/testtoken123',ok=True,error=''))
print('Finished')
''', encoding="utf-8")
        jobs = [{"jobname": "test_one", "receptor_pdb": str(self.pdb()), "ligand_pdb": str(self.pdb()), "email": ""}]
        runner = BatchRunner(str(script), sys.executable, self.root / "output")
        runner.run(jobs, delay=0)
        runner.run(jobs, delay=0)
        logs = read_log(self.root / "output" / "run-log.csv")
        self.assertEqual(len(logs), 1)
        self.assertTrue(accepted(logs[0]))

    def test_uncertain_interruption_blocks_resubmission(self):
        script = self.root / "stub.py"
        script.write_text("")
        output = self.root / "output"
        output.mkdir()
        (output / "submission-in-flight.json").write_text(json.dumps({"attempt": str(self.root / "missing")}))
        with self.assertRaisesRegex(ValueError, "interrumpido"):
            BatchRunner(str(script), sys.executable, output).run([])

    def test_collection_can_retry_pending_without_resubmission(self):
        pipeline = self.pipeline()
        pipeline.config["jobs"] = [{"jobname": "pair", "RBP": "P09651", "Receptor": "P00533", "Categoria_Receptor": "A"}]
        with (pipeline.directory / "run-log.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
            writer.writeheader()
            writer.writerow({"jobname": "pair", "token": "token", "ok": True, "result_url": "http://hdock.phys.hust.edu.cn/data/token"})
        with patch("pipeline.fetch_score", side_effect=[(None, "Running"), (-180.25, HTML)]) as fetch:
            pipeline.collect()
            self.assertEqual(pipeline.table().iloc[0]["Estado"], "pendiente_o_formato_desconocido")
            pipeline.collect()
            pipeline.collect()
            self.assertEqual(fetch.call_count, 2)
        self.assertEqual(pipeline.table().iloc[0]["Docking_Score"], -180.25)
        self.assertEqual(len(read_log(pipeline.directory / "run-log.csv")), 1)

    def test_changed_token_does_not_reuse_old_score(self):
        from results_parser import summary
        log = self.root / "run-log.csv"
        with log.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
            writer.writeheader()
            writer.writerow({"jobname": "pair", "token": "new", "ok": True, "result_url": "http://hdock.phys.hust.edu.cn/data/new"})
        frame = summary([{"jobname": "pair", "RBP": "x", "Receptor": "y", "Categoria_Receptor": "A"}], log,
                        {"pair": {"token": "old", "score": -100, "state": "completado"}})
        self.assertEqual(frame.iloc[0]["Estado"], "enviado")
        self.assertTrue(__import__('pandas').isna(frame.iloc[0]["Docking_Score"]))


if __name__ == "__main__":
    unittest.main()
