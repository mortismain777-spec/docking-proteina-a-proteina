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
INPUT = "tipo,identificador,nombre_comun,categoria\nligando,P09651,Ligando1,\nreceptor,P00533,EGFR,A\n"
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
        self.assertEqual(len(read_inputs(INPUT + "RBP,P09651,Ligando1,\n")), 2)
        with self.assertRaises(ValueError):
            read_inputs(INPUT + "receptor,P00533,EGFR,B\n")

    def test_ligando_accepts_legacy_csv_and_preserves_structure_keys(self):
        current = read_inputs(INPUT)
        legacy = read_inputs(INPUT.replace('ligando,', 'RBP,'))
        self.assertEqual(current, legacy)
        self.assertEqual(current[0]['tipo'], 'ligando')
        self.assertEqual(protein_key(current[0]), 'RBP:P09651')

    def test_legacy_batch_keeps_jobnames_tokens_scores_and_local_pdb(self):
        pipeline = self.pipeline()
        path = self.pdb()
        with patch('pipeline.StructureFetcher.fetch', return_value={
            'path': str(path), 'sha256': sha256(path), 'source': 'fixture'
        }):
            pipeline.prepare()
        original_names = [job['jobname'] for job in pipeline.config['jobs']]
        pipeline.config['proteins'][0]['tipo'] = 'RBP'
        pipeline.config['local_pdb']['RBP:P09651'] = str(path)
        for job in pipeline.config['jobs']:
            job['RBP'] = job.pop('Ligando')
        pipeline.config['results'][original_names[0]] = {
            'token': 'old_token', 'score': -206.95, 'state': 'completado'
        }
        BatchRunner('', sys.executable, pipeline.directory)._append({
            'jobname': original_names[0], 'token': 'old_token', 'ok': True,
            'result_url': 'http://hdock.phys.hust.edu.cn/data/old_token/'
        })
        pipeline.save()
        restored = Pipeline.load(pipeline.directory)
        self.assertEqual(restored.config['proteins'][0]['tipo'], 'ligando')
        self.assertEqual(restored.table().iloc[0]['Ligando'], 'P09651')
        self.assertEqual(restored.table().iloc[0]['Job_Token'], 'old_token')
        self.assertEqual(restored.table().iloc[0]['Docking_Score'], -206.95)
        self.assertEqual(restored.config['local_pdb']['RBP:P09651'], str(path))
        with patch('pipeline.StructureFetcher.fetch', side_effect=AssertionError('No redescargar')):
            restored.prepare()
        self.assertEqual([job['jobname'] for job in restored.config['jobs']], original_names)
        self.assertEqual(restored.table().iloc[0]['Job_Token'], 'old_token')

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

    def test_canonical_model_is_selected_and_requested_domain_cropped(self):
        client = Mock()
        response = Mock()
        response.json.return_value = [
            {"uniprotAccession": "P00533-2", "pdbUrl": "https://example.invalid/isoform"},
            {"uniprotAccession": "P00533", "pdbUrl": "https://example.invalid/canonical"},
        ]
        atoms = PDB.splitlines()[0]
        pdb = "\n".join(atoms[:22] + f"{n:4d}" + atoms[26:] for n in range(1, 5)) + "\nEND\n"
        client.get.side_effect = [response, Mock(content=pdb.encode())]
        result = StructureFetcher(self.root / "domain", client=client).fetch("P00533", residue_range=(2, 3))
        self.assertEqual(client.get.call_args.args[0], 'https://example.invalid/canonical')
        positions = {int(line[22:26]) for line in Path(result['path']).read_text().splitlines() if line.startswith('ATOM  ')}
        self.assertEqual(positions, {2, 3})
        self.assertEqual(result['residue_range'], [2, 3])
        self.assertNotEqual(result['full_structure_sha256'], result['sha256'])

    def test_domain_requires_complete_range_and_input_validates_bounds(self):
        fetcher = StructureFetcher(self.root / 'domain')
        with self.assertRaisesRegex(ValueError, 'no cubre'):
            fetcher.fetch('LOCAL', str(self.pdb()), residue_range=(1, 2))
        with self.assertRaisesRegex(ValueError, 'residuo_inicio'):
            read_inputs('tipo,identificador,nombre_comun,categoria,residuo_inicio,residuo_fin\nligando,P00648,x,,20,10\nreceptor,P11540,y,A,,\n')

    def test_changed_domain_cannot_reuse_prepared_structure(self):
        pipeline = self.pipeline()
        path = self.pdb()
        with patch('pipeline.StructureFetcher.fetch', return_value={
            'path': str(path), 'sha256': sha256(path), 'source': 'fixture'
        }):
            pipeline.prepare()
        pipeline.config['proteins'][0].update(residuo_inicio=1, residuo_fin=1)
        pipeline.prepare()
        self.assertIn('rango de residuos cambió', pipeline.config['errors']['RBP:P09651'])
        self.assertEqual(pipeline.config['jobs'], [])

    def test_experimental_controls_can_exclude_optional_references(self):
        text = ('tipo,identificador,nombre_comun,categoria,residuo_inicio,residuo_fin\n'
                'ligando,Q15116,PD-1,,25,170\n'
                'receptor,Q9NZQ7,PD-L1,A,19,238\n'
                'receptor,P33681,CD80,control,35,242\n')
        items = read_inputs(text)
        pipeline = Pipeline.create(self.root / 'benchmark', items, 9606, {}, False, '', albumin=False)
        path = self.pdb()
        with patch('pipeline.StructureFetcher.fetch', return_value={'path': str(path), 'sha256': sha256(path), 'source': 'fixture'}) as fetch:
            pipeline.prepare()
        self.assertEqual(len(pipeline.config['proteins']), 3)
        self.assertEqual(len(pipeline.config['jobs']), 2)
        self.assertEqual([call.kwargs['residue_range'] for call in fetch.call_args_list], [(25,170), (19,238), (35,242)])
        self.assertEqual(sum(j['Categoria_Receptor'] == 'control' for j in pipeline.config['jobs']), 1)

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

    def test_hdock_scores_in_metric_rows(self):
        html = ("<table><tr><th>Rank</th><td>1</td><td>2</td></tr>"
                "<tr><th>Docking Score</th><td>-206.95</td><td>-177.55</td></tr>"
                "<tr><th>Confidence Score</th><td>0.7575</td><td>0.6344</td></tr>"
                "<tr><th>Ligand rmsd</th><td>67.75</td><td>78.49</td></tr></table>")
        self.assertEqual(best_score(html), -206.95)
        self.assertEqual(best_score(html.replace('-177.55', '-250.00')), -250.00)

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
