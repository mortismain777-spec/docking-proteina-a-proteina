"""Pruebas de fuentes alternativas, caché, numeración y reanudación sin red."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

from data_fetcher import StructureFetcher, StructureUnavailable, ESMFOLD_URL
from structure_cache import pdb_info
from pipeline import Pipeline, read_inputs
from test_pipeline import PDB


def response(status=200, text='', url='https://alphafold.ebi.ac.uk/api/prediction/P00533'):
    r=requests.Response(); r.status_code=status; r._content=text.encode(); r.url=url
    return r


def model():
    line=PDB.splitlines()[0]
    return '\n'.join([line[:17]+'ALA'+line[20:22]+'   1'+line[26:60]+' 80.00'+line[66:],
                     line[:17]+'GLY'+line[20:22]+'   2'+line[26:60]+' 40.00'+line[66:],'END'])+'\n'


class StructureSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fetcher(self,client,**kwargs):
        return StructureFetcher(self.root/'structures',client=client,cache_directory=self.root/'cache',**kwargs)

    def fallback_client(self,sequence='AG'):
        client=Mock()
        client.get.side_effect=[response(404),response(text='>sp|P00533|test\n'+sequence)]
        client.post.return_value=response(text=model(),url=ESMFOLD_URL)
        return client

    def test_404_folds_domain_remaps_and_reuses_cache_offline(self):
        client=self.fallback_client('AAAAAG')
        result=self.fetcher(client).fetch('P00533',residue_range=(5,6))
        self.assertEqual(client.post.call_args.kwargs['data'],b'AG')
        self.assertEqual(result['structure_source'],'ESMFold')
        self.assertEqual(result['structure_status'],'FALLBACK_OK')
        self.assertEqual(result['mean_plddt'],60)
        self.assertEqual(result['pct_plddt_below_50'],50)
        atoms=[line for line in Path(result['path']).read_text().splitlines() if line.startswith('ATOM')]
        self.assertEqual([int(line[22:26]) for line in atoms],[5,6])
        offline=Mock(); offline.get.side_effect=AssertionError('No consultar APIs')
        again=self.fetcher(offline).fetch('P00533',residue_range=(5,6))
        self.assertTrue(again['cache_hit'])
        self.assertEqual(again['sha256'],result['sha256'])
        self.assertIsNone(self.fetcher(offline).cache.find('P00533',9606,None,'',True))
        self.assertIsNone(self.fetcher(offline).cache.find('P00533',9606,(5,6),'B',True))
        self.assertIsNone(self.fetcher(offline).cache.find('P00533',9606,(5,6),'',False))

    def test_transient_failure_does_not_invent_absence_or_predict(self):
        client=Mock(); client.get.side_effect=requests.Timeout('offline')
        with self.assertRaisesRegex(StructureUnavailable,'RETRY_PENDING'):
            self.fetcher(client).fetch('P00533')
        client.post.assert_not_called()

    def test_404_from_pdb_link_does_not_trigger_fallback(self):
        client=Mock()
        client.get.side_effect=[response(text=json.dumps([{'pdbUrl':'https://example.org/model.pdb'}])),
                                response(404,url='https://example.org/model.pdb')]
        with self.assertRaises(requests.HTTPError): self.fetcher(client).fetch('P00533')
        client.post.assert_not_called()

    def test_no_fallback_keeps_explicit_local_and_na_confidence(self):
        local=self.root/'manual.pdb'; local.write_text(model())
        client=Mock(); client.get.side_effect=AssertionError('No red')
        result=self.fetcher(client,allow_fallback=False).fetch('NOMBRE',str(local))
        self.assertEqual(result['structure_source'],'Local')
        self.assertIsNone(result['mean_plddt'])
        client.get.side_effect=None; client.get.return_value=response(404)
        with self.assertRaises(requests.HTTPError): self.fetcher(client,allow_fallback=False).fetch('P00533')
        client.post.assert_not_called()

    def test_rejects_wrong_sequence_and_oversized_sequence(self):
        client=self.fallback_client('AA')
        with self.assertRaisesRegex(ValueError,'no coincide'): self.fetcher(client).fetch('P00533')
        self.assertFalse(list((self.root/'cache').glob('*.pdb')))
        client=self.fallback_client('A'*401)
        with self.assertRaisesRegex(StructureUnavailable,'No se truncó'): self.fetcher(client).fetch('P00533')
        client.post.assert_not_called()

    def test_invalid_cache_hash_is_ignored(self):
        client=self.fallback_client(); self.fetcher(client).fetch('P00533')
        next((self.root/'cache').glob('*.pdb')).write_text('HTML corrupto')
        client=self.fallback_client(); result=self.fetcher(client).fetch('P00533')
        self.assertFalse(result['cache_hit']); client.post.assert_called_once()

    def test_esm_historical_confidence_scale_does_not_create_false_warning(self):
        path=self.root/'historical.pdb'
        path.write_text(model().replace(' 80.00','  0.80').replace(' 40.00','  0.40'))
        self.assertAlmostEqual(pdb_info(path,'ESMFold')['mean_plddt'],60)
        self.assertEqual(pdb_info(path,'ESMFold')['pct_plddt_below_50'],50)
        self.assertIsNone(pdb_info(path,'Local')['mean_plddt'])

    def test_refseq_retains_version_and_does_not_query_alphafold(self):
        client=Mock(); client.get.return_value=response(text='>NP_123456.2\nAG')
        client.post.return_value=response(text=model(),url=ESMFOLD_URL)
        result=self.fetcher(client).fetch('NP_123456.2')
        self.assertEqual(result['resolved_accession'],'NP_123456.2')
        self.assertEqual(client.get.call_args.kwargs['params']['id'],'NP_123456.2')
        self.assertNotIn('alphafold',client.get.call_args.args[0])

    def test_retry_after_three_total_attempts_and_stop(self):
        client=Mock(); limited=response(429); limited.headers['Retry-After']='7'
        client.post.side_effect=[limited,response(503),response(text=model())]
        fetcher=self.fetcher(client)
        with patch.object(fetcher,'_wait') as wait:
            fetcher._request('post',ESMFOLD_URL,data=b'AG',timeout=300)
        self.assertEqual(client.post.call_count,3)
        self.assertIn(7,[call.args[0] for call in wait.call_args_list])
        stop=threading.Event(); stop.set()
        with self.assertRaises(InterruptedError): self.fetcher(client,stop=stop).fetch('P00533')

    def test_csv_local_reports_and_previous_job_identity(self):
        local=self.root/'manual.pdb'; local.write_text(model())
        text=f'tipo,identificador,nombre_comun,categoria,pdb_local\nligando,P00533,x,,{local}\nreceptor,Q15116,y,A,{local}\n'
        items=read_inputs(text)
        batch=Pipeline.create(self.root/'batch',items,9606,{},False,'',albumin=False,cache_directory=self.root/'cache')
        batch.prepare()
        self.assertEqual(len(batch.config['jobs']),1)
        self.assertEqual(batch.table().iloc[0]['Fuente_Ligando'],'Local')
        names=[j['jobname'] for j in batch.config['jobs']]
        batch.prepare()
        self.assertEqual(names,[j['jobname'] for j in batch.config['jobs']])
        report=(batch.directory/'structure_report.csv').read_text(encoding='utf-8-sig')
        self.assertIn('Local,NA',report)
        self.assertEqual((batch.directory/'needs_manual_modeling.txt').read_text(),'')

    def test_partial_failure_and_stop_still_write_report_without_docking_log(self):
        text='tipo,identificador,nombre_comun,categoria\nligando,P00533,x,\nreceptor,Q15116,y,A\n'
        batch=Pipeline.create(self.root/'partial',read_inputs(text),9606,{},False,'',albumin=False)
        with patch('pipeline.StructureFetcher.fetch',side_effect=StructureUnavailable('RETRY_PENDING: red')):
            batch.prepare()
        self.assertIn('RETRY_PENDING',(batch.directory/'structure_report.csv').read_text())
        self.assertFalse((batch.directory/'run-log.csv').exists())
        stop=threading.Event(); stop.set(); batch.prepare(stop=stop)
        self.assertEqual(len(batch.config['jobs']),0)


if __name__=='__main__': unittest.main()
