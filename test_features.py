"""Pruebas de preparación, modelos, seguimiento y aislamiento del modo local."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from data_fetcher import StructureFetcher
from job_runner import BatchRunner
from local_engine import LocalEngine, native_scores, split_models
from model_files import download_models, viewer_copy
from pipeline import Pipeline, read_inputs
from preparation import prepare_protein
from result_monitor import MonitorLock, cycle, running
from test_pipeline import PDB, INPUT

HTML = '<table><tr><td>Rank</td><td>1</td></tr><tr><td>Docking Score</td><td>-206.95</td></tr></table><a href="model_1.pdb">1</a>'


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self):
        path = self.root / 'protein.pdb'
        path.write_text(PDB)
        return path

    def batch(self):
        pipeline = Pipeline.create(self.root / 'batch', read_inputs(INPUT), 9606, {}, False, '', albumin=False)
        pipeline.config['jobs'] = [{'jobname':'pair','Ligando':'P09651','Receptor':'P00533','Categoria_Receptor':'A',
                                  'receptor_pdb':str(self.source()),'ligand_pdb':str(self.source())}]
        pipeline.save()
        BatchRunner('',sys.executable,pipeline.directory)._append({'jobname':'pair','token':'token123',
            'result_url':'http://hdock.phys.hust.edu.cn/data/token123/','ok':True})
        return pipeline

    def test_names_resolve_uniquely_and_keep_taxon(self):
        client = Mock()
        client.get.return_value.json.return_value = {'results':[{'primaryAccession':'Q15116'}]}
        accession = StructureFetcher(self.root,9606,client).resolve('Programmed cell death protein 1')
        self.assertEqual(accession,'Q15116')
        self.assertIn('protein_name:',client.get.call_args.kwargs['params']['query'])
        self.assertIn('organism_id:9606',client.get.call_args.kwargs['params']['query'])

    def test_preparation_records_geometry_and_removes_heteroatoms(self):
        source=self.source()
        source.write_text(PDB + PDB.splitlines()[0].replace('ATOM  ','HETATM') + '\n')
        result=prepare_protein(source,self.root/'prepared.pdb')
        self.assertEqual(result['atoms'],1)
        self.assertEqual(result['removed_atoms'],1)
        self.assertEqual(result['bounding_center_A'],[12,13,14])
        self.assertTrue(result['warnings'])
        self.assertNotIn('HETATM',(self.root/'prepared.pdb').read_text())

    def test_viewer_copy_separates_same_chain_ids_without_moving_atoms(self):
        source=self.source()
        atom=PDB.splitlines()[0]
        source.write_text(atom+'\nTER\n'+atom+'\nTER\nEND\n')
        result=viewer_copy(source,self.root/'viewer.pdb')
        lines=[line for line in Path(result['path']).read_text().splitlines() if line.startswith('ATOM')]
        self.assertEqual([line[21] for line in lines],['A','B'])
        self.assertEqual([line[30:54] for line in lines],[atom[30:54]]*2)

    def test_download_only_links_in_this_job_and_skip_template_zero(self):
        client=Mock()
        client.get.return_value=Mock(status_code=200,content=PDB.encode())
        html=HTML+'<a href="http://other.invalid/model_2.pdb">x</a><a href="../other/model_2.pdb">x</a><a href="model_0.pdb">0</a>'
        records=download_models('http://hdock.phys.hust.edu.cn/data/token123/',html,self.root/'models',1,client)
        self.assertEqual(records[0]['rank'],1)
        self.assertEqual(client.get.call_count,1)
        self.assertTrue(Path(records[0]['viewer']['path']).exists())
        download_models('http://hdock.phys.hust.edu.cn/data/token123/',html,self.root/'models',1,client)
        self.assertEqual(client.get.call_count,1)
        self.assertTrue((self.root/'models/abrir_chimerax.cxc').exists())

    def test_local_scores_and_model_split(self):
        output=self.root/'hdock.out'
        output.write_text('Grid spacing: 1.200\n0 0 0 0 0 0 -123.5 0.3 1 1\n0 0 0 0 0 0 -100 0.5 1 2\n')
        self.assertEqual(native_scores(output),[-123.5,-100])
        combined=self.root/'combined.pdb'
        combined.write_text('MODEL 1\n'+PDB+'ENDMDL\nMODEL 2\n'+PDB+'ENDMDL\n')
        self.assertEqual(len(split_models(combined,self.root/'models',2)),2)

    def test_monitor_lock_prevents_two_watchers(self):
        lock=MonitorLock(self.root)
        self.assertTrue(lock.acquire())
        self.assertTrue(running(self.root))
        lock.close()
        self.assertFalse(running(self.root))

    def test_ready_notification_is_deduplicated_and_tokens_preserved(self):
        pipeline=self.batch()
        with patch('pipeline.fetch_score',return_value=(-206.95,HTML)), patch('result_monitor.notify',return_value=(True,'')) as toast:
            state=cycle(pipeline.directory,{},0,True)
            self.assertEqual(state['status'],'completado')
            self.assertEqual(toast.call_count,1)
            cycle(pipeline.directory,state,0,True)
            self.assertEqual(toast.call_count,1)
        original=Pipeline.load(pipeline.directory)
        self.assertEqual(original.table().iloc[0]['Job_Token'],'token123')
        self.assertEqual(original.table().iloc[0]['Docking_Score'],-206.95)
        with (pipeline.directory/'run-log.csv').open() as handle:
            self.assertEqual(len(list(csv.DictReader(handle))),1)

    def test_download_error_does_not_discard_available_score(self):
        pipeline=self.batch()
        with patch('pipeline.fetch_score',return_value=(-206.95,HTML)), patch('model_files.download_models',side_effect=RuntimeError('network')):
            pipeline.collect(download_count=1)
        result=pipeline.table().iloc[0]
        self.assertEqual(result['Estado'],'completado')
        self.assertEqual(result['Docking_Score'],-206.95)
        self.assertEqual(result['Error_Descarga'],'network')

    def test_monitor_waits_for_actual_score_before_notifying(self):
        pipeline=self.batch()
        with patch('pipeline.fetch_score',return_value=(None,'Job is running')), patch('result_monitor.notify',return_value=(True,'')) as toast:
            state=cycle(pipeline.directory,{},0,True)
            self.assertEqual(state['status'],'consultando')
            self.assertEqual(toast.call_count,0)
        with patch('pipeline.fetch_score',return_value=(-206.95,HTML)), patch('result_monitor.notify',return_value=(True,'')) as toast:
            state=cycle(pipeline.directory,state,0,True)
            self.assertEqual(state['status'],'completado')
            self.assertEqual(toast.call_count,1)

    def test_local_and_remote_results_never_mix(self):
        pipeline=self.batch()
        pipeline.config['results']['pair']={'token':'token123','state':'completado','score':-206.95}
        pipeline.config['local_results']={'pair':{'state':'completado','score':-100,'models':[]}}
        self.assertEqual(pipeline.table().iloc[0]['Docking_Score'],-206.95)
        self.assertEqual(pipeline.table('local').iloc[0]['Docking_Score'],-100)
        self.assertEqual(pipeline.table('local').iloc[0]['Job_Token'],'')

    def test_local_adapter_runs_processes_and_resumes_without_cloud(self):
        pipeline=self.batch()
        engine=LocalEngine(str(self.root))
        engine.use_wsl=False
        engine.check=lambda: {}
        hdock=self.root/'hdock'
        hdock.write_text("import pathlib,sys\np=pathlib.Path(sys.argv[sys.argv.index('-out')+1]);p.write_text('0 0 0 0 0 0 -123.5 0.3 1 1\\n')\n")
        createpl=self.root/'createpl'
        createpl.write_text('import pathlib,sys\npathlib.Path(sys.argv[2]).write_text('+repr('MODEL 1\n'+PDB+'ENDMDL\n')+')\n')
        # El adaptador se ejerce con subprocesos Python reales que simulan los binarios.
        native_run=engine._run
        engine._run=lambda command,console:native_run([sys.executable]+command,console)
        local={}
        engine.run(pipeline.config['jobs'],pipeline.directory,local,count=1)
        self.assertEqual(local['pair']['score'],-123.5)
        self.assertEqual(len(local['pair']['models']),1)
        with patch.object(engine,'_run',side_effect=AssertionError('No recalcular')):
            engine.run(pipeline.config['jobs'],pipeline.directory,local,count=1)


if __name__=='__main__':
    unittest.main()
