"""Orden de proveedores, respaldo tras 504 y selección estructural conservadora."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
from data_fetcher import StructureFetcher, StructureUnavailable
from provider_settings import DEFAULT_ORDER, validate_order, policy_from_config
from structure_providers import pdb_chain_lines, fetch_swiss_repository, _write_checked, ProviderMiss
from structure_cache import StructureCache, pdb_info
from test_structure_sources import model, response
from pipeline import Pipeline, read_inputs

CIF='''data_test
loop_
_atom_site.group_PDB
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.label_comp_id
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.type_symbol
_atom_site.pdbx_PDB_model_num
ATOM X 1 ALA CA . 12 13 14 1 20 C 1
ATOM X 2 GLY CA . 15 16 17 1 30 C 1
'''


class ProviderOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.path=self.root/'model.pdb'; self.path.write_text(model())

    def tearDown(self): self.temp.cleanup()

    def fetcher(self,order,**kwargs):
        return StructureFetcher(self.root/'structures',client=Mock(),provider_order=order,use_structure_cache=False,**kwargs)

    def result(self,method):
        return {'path':str(self.path),'source':'https://example.invalid/model','structure_source':method,'structure_status':'OK'}

    def test_selected_order_is_used_without_trying_lower_provider(self):
        f=self.fetcher(['esmfold','alphafold'])
        with patch.object(f,'_fold',return_value=self.result('ESMFold')) as fold, patch.object(f,'_fetch_primary') as af:
            result=f.fetch('P00533')
        fold.assert_called_once(); af.assert_not_called()
        self.assertEqual(result['provider_id'],'esmfold')
        self.assertEqual(result['provider_order_used'],['esmfold','alphafold'])

    def test_504_continues_to_configured_provider_and_preserves_trace(self):
        f=self.fetcher(['esmfold','swissmodel'],continue_provider_errors=True)
        error=requests.HTTPError('gateway',response=response(504))
        with patch.object(f,'_fold',side_effect=error), patch('structure_providers.fetch_swiss_repository',return_value=self.result('SWISS-MODEL Repository')):
            result=f.fetch('P00533')
        self.assertEqual(result['provider_attempts'][0]['status'],'RETRY_PENDING')
        self.assertEqual(result['provider_attempts'][1]['provider'],'swissmodel')
        self.assertIsNone(result['mean_plddt'])

    def test_stop_on_transient_option_does_not_call_next_provider(self):
        f=self.fetcher(['esmfold','swissmodel'],continue_provider_errors=False)
        with patch.object(f,'_fold',side_effect=requests.Timeout('slow')), patch('structure_providers.fetch_swiss_repository') as swiss:
            with self.assertRaisesRegex(StructureUnavailable,'RETRY_PENDING'): f.fetch('P00533')
        swiss.assert_not_called()

    def test_no_fallback_still_means_only_alphafold(self):
        f=self.fetcher(['swissmodel','esmfold'],allow_fallback=False)
        with patch.object(f,'_fetch_primary',return_value={**self.result('AlphaFold'),'uniprot':'P00533'}) as af, patch.object(f,'_fold') as fold:
            f.fetch('P00533')
        af.assert_called_once(); fold.assert_not_called()

    def test_cache_ranks_enabled_sources_and_does_not_invent_plddt(self):
        cache=StructureCache(self.root/'cache')
        for method in ['AlphaFold','SWISS-MODEL Repository']:
            cache.store(self.path,self.result(method),'P00533','P00533',9606,None,'')
        _,meta=cache.find('P00533',9606,None,'',True,['swissmodel','alphafold'])
        self.assertEqual(meta['structure_source'],'SWISS-MODEL Repository'); self.assertIsNone(meta['mean_plddt'])
        self.assertIsNone(cache.find('P00533',9606,None,'',True,['pdb']))

    def test_sifts_maps_label_number_to_uniprot_without_moving_coordinates(self):
        mappings=[{'chain_id':'A','struct_asym_id':'X','start':{'residue_number':1},'end':{'residue_number':2},'unp_start':5,'unp_end':6}]
        lines,details=pdb_chain_lines(CIF,mappings,'P00533','A','AAAAAG',(5,6))
        self.assertEqual([int(line[22:26]) for line in lines],[5,6])
        self.assertEqual([float(lines[0][30:38]),float(lines[0][38:46]),float(lines[0][46:54])],[12,13,14])
        fake=Mock(directory=self.root)
        result=_write_checked(fake,'P00533','pdb',lines,'AAAAAG',5,6,{})
        self.assertEqual(pdb_info(result['path'])['sequence'],'AG')
        with self.assertRaises(ProviderMiss): pdb_chain_lines(CIF.replace('GLY','SER'),mappings,'P00533','A','AAAAAG',(5,6))
        with self.assertRaises(ValueError): _write_checked(fake,'P00533','pdb',lines[:1],'AAAAAG',5,6,{})

    def test_swiss_filters_alphafold_mirrors_and_keeps_quality_separate(self):
        models=[{'provider':'ALPHAFOLD','from':1,'to':2,'template':'1abc.1.A'},
                {'provider':'SWISSMODEL','from':1,'to':2,'template':'1xyz.1.A','gmqe':0.8,'qmean':{'avg_local_score':0.7}}]
        f=Mock(directory=self.root,chains='')
        f.sequence.return_value='AG'
        f._request.side_effect=[response(text=json.dumps({'result':{'structures':models}})),response(text=model(),url='https://swissmodel.expasy.org/model.pdb')]
        result=fetch_swiss_repository(f,'P00533',None)
        self.assertEqual(result['template'],'1xyz.1.A')
        self.assertEqual(result['quality_metrics']['GMQE'],0.8)
        self.assertIsNone(pdb_info(result['path'],result['structure_source'])['mean_plddt'])

    def test_policy_validation_and_legacy_defaults(self):
        self.assertEqual(policy_from_config({})['provider_order'],['alphafold','esmfold'])
        for invalid in ([],['paid'],['pdb','pdb']):
            with self.assertRaises(ValueError): validate_order(invalid)
        self.assertEqual(validate_order(DEFAULT_ORDER),DEFAULT_ORDER)

    def test_policy_roundtrip_and_legacy_provenance_view_does_not_mutate_jobs(self):
        items=read_inputs('tipo,identificador,nombre_comun,categoria\nligando,P00533,x,\nreceptor,Q15116,y,A\n')
        batch=Pipeline.create(self.root/'batch',items,9606,{},False,'',albumin=False,
                              provider_order=['swissmodel','esmfold'],use_structure_cache=False,continue_provider_errors=True)
        restored=Pipeline.load(batch.directory)
        self.assertEqual(restored.config['provider_order'],['swissmodel','esmfold'])
        self.assertFalse(restored.config['use_structure_cache'])
        job={'jobname':'old_name','Ligando':'P00533','Receptor':'Q15116','Categoria_Receptor':'A'}
        restored.config['jobs']=[job]
        restored.config['structures']={'RBP:P00533':{'source':'https://alphafold.ebi.ac.uk/files/old.pdb'}}
        table=restored.table()
        self.assertEqual(table.iloc[0]['Fuente_Ligando'],'AlphaFold')
        self.assertNotIn('Fuente_Ligando',job)
        self.assertEqual(table.iloc[0]['Jobname'],'old_name')


if __name__=='__main__': unittest.main()
