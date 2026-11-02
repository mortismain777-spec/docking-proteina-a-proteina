"""Fuentes gratuitas de estructuras existentes, con secuencia y numeración verificadas."""
from __future__ import annotations
import hashlib
import math
import re
from pathlib import Path
import requests
from structure_cache import AA, pdb_info


class ProviderMiss(ValueError):
    pass


def _range(sequence, residue_range):
    start,end=residue_range or (1,len(sequence))
    if not 1 <= start <= end <= len(sequence) or end > 9999:
        raise ValueError('INPUT_ERROR: rango fuera de la secuencia o de la numeración PDB.')
    return start,end


def _write_checked(fetcher, accession, provider, lines, sequence, start, end, metadata):
    """Exigir todos los residuos solicitados, identidad exacta y una única cadena."""
    target=fetcher.directory/(hashlib.sha256((accession+provider+str((start,end))).encode()).hexdigest()[:20]+'.pdb')
    temporary=target.with_suffix('.part')
    try:
        temporary.write_text('\n'.join(lines+['TER','END'])+'\n',encoding='utf-8')
        info=pdb_info(temporary,'',sequence[start-1:end])
        atoms=[line for line in lines if line.startswith('ATOM  ')]
        if len(info['chains']) != 1 or {int(line[22:26]) for line in atoms if line[12:16].strip()=='CA'} != set(range(start,end+1)):
            raise ProviderMiss('El modelo no cubre todos los residuos solicitados con numeración inequívoca.')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {'path':str(target.resolve()),'uniprot':accession,'resolved_accession':accession,
            'provider_id':provider,'structure_status':'FALLBACK_OK',
            'residue_range':[start,end] if (start,end)!=(1,len(sequence)) else None,
            'input_sequence_sha256':hashlib.sha256(sequence.encode()).hexdigest(),
            'numbering_map':{'pdb_uses_original_numbering':True,'original_start':start,'length':end-start+1},
            **metadata}


def pdb_chain_lines(cif_text, mappings, accession, chain_id, sequence, residue_range):
    """SIFTS usa label_seq_id, no el número de residuo del autor. No alinear por intuición."""
    import gemmi
    start,end=_range(sequence,residue_range)
    segments=[m for m in mappings if m.get('chain_id')==chain_id]
    position_map={}
    asym_ids=set()
    for segment in segments:
        label_start=int(segment['start']['residue_number']); label_end=int(segment['end']['residue_number'])
        unp_start,unp_end=int(segment['unp_start']),int(segment['unp_end'])
        if label_end-label_start != unp_end-unp_start:
            continue
        asym=segment['struct_asym_id']; asym_ids.add(asym)
        for label,original in zip(range(label_start,label_end+1),range(unp_start,unp_end+1)):
            key=(asym,label)
            if key in position_map and position_map[key]!=original:
                raise ProviderMiss('Mapeo SIFTS contradictorio.')
            position_map[key]=original
    if len(asym_ids)!=1 or len(chain_id)!=1:
        raise ProviderMiss('Cadena o mapeo SIFTS no inequívoco para formato PDB.')
    block=gemmi.cif.read_string(cif_text).sole_block()
    tags=['group_PDB','label_asym_id','label_seq_id','label_comp_id','label_atom_id','label_alt_id',
          'Cartn_x','Cartn_y','Cartn_z','occupancy','B_iso_or_equiv','type_symbol','pdbx_PDB_model_num']
    table=block.find('_atom_site.',tags)
    if not table: raise ProviderMiss('mmCIF sin campos atómicos requeridos.')
    atoms={}; first_model=None
    for row in table:
        values=[row.str(i) for i in range(len(tags))]
        group,asym,label,residue,atom,alt,x,y,z,occupancy,bfactor,element,model=values
        if group!='ATOM' or asym not in asym_ids: continue
        if first_model is None: first_model=model
        if model!=first_model or not label.isdigit(): continue
        position=position_map.get((asym,int(label)))
        if position is None or not start<=position<=end: continue
        if residue not in AA or AA[residue]!=sequence[position-1]:
            raise ProviderMiss('La cadena experimental contiene mutaciones o residuos no estándar en la región solicitada.')
        numbers=[float(v) for v in (x,y,z,occupancy,bfactor)]
        if not all(math.isfinite(n) for n in numbers): raise ProviderMiss('Coordenadas no finitas.')
        if any(abs(n)>=1000 for n in numbers[:3]) or len(atom)>4 or len(element)>2:
            raise ProviderMiss('Átomos no representables con seguridad en PDB.')
        key=(position,atom)
        score=(float(occupancy),alt in ('.','?',''))
        if key not in atoms or score>atoms[key][0]: atoms[key]=(score,residue,numbers,element)
    lines=[]
    for serial,((position,atom),(_,residue,numbers,element)) in enumerate(sorted(atoms.items()),1):
        if serial>99999: raise ProviderMiss('Demasiados átomos para formato PDB.')
        x,y,z,occupancy,bfactor=numbers
        name=f' {atom:<3}' if len(atom)<4 and len(element)==1 else f'{atom:>4}'
        lines.append(f'ATOM  {serial:5d} {name} {residue:3s} {chain_id}{position:4d}    {x:8.3f}{y:8.3f}{z:8.3f}{occupancy:6.2f}{bfactor:6.2f}          {element:>2}')
    return lines, {'author_chain':chain_id,'label_asym_id':next(iter(asym_ids)),
                   'model_number':first_model,'mapping_source':'PDBe SIFTS; label_seq_id → UniProt',
                   'note':'Cadena aislada; sin otras cadenas, ligandos ni cofactores. Revisar estado biológico antes del docking.'}


def fetch_pdb_repository(fetcher, accession, residue_range):
    if '-' in accession: raise ProviderMiss('PDB automático requiere accession canónico; no se sustituye una isoforma.')
    sequence=fetcher.sequence(accession); start,end=_range(sequence,residue_range)
    url=f'https://www.ebi.ac.uk/pdbe/api/mappings/best_structures/{accession}'
    candidates=fetcher._request('get',url,timeout=(10,60)).json().get(accession,[])
    seen=set(); errors=[]; count=0
    for item in candidates:
        if count>=8: break
        pdb_id=str(item.get('pdb_id','')).lower(); chain=str(item.get('chain_id',''))
        if not re.fullmatch('[0-9][a-z0-9]{3}',pdb_id) or (pdb_id,chain) in seen: continue
        if fetcher.chains and chain not in [c.strip() for c in fetcher.chains.split(',')]: continue
        if int(item.get('unp_start',0))>start or int(item.get('unp_end',0))<end: continue
        seen.add((pdb_id,chain)); count+=1
        try:
            mapping_url=f'https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/{pdb_id}'
            data=fetcher._request('get',mapping_url,timeout=(10,60)).json()
            mappings=data.get(pdb_id,{}).get('UniProt',{}).get(accession,{}).get('mappings',[])
            origin=f'https://files.rcsb.org/download/{pdb_id.upper()}.cif'
            response=fetcher._request('get',origin,timeout=(10,90))
            lines,details=pdb_chain_lines(response.text,mappings,accession,chain,sequence,residue_range)
            return _write_checked(fetcher,accession,'pdb',lines,sequence,start,end,
                {'structure_source':'PDB (PDBe)','source':origin,'source_entry':pdb_id.upper()+':'+chain,
                 'prediction_method':'Estructura experimental; '+str(item.get('experimental_method','')),
                 'quality_metrics':{'resolution_A':item.get('resolution')},'selection':details,
                 'remote_structure_sha256':hashlib.sha256(response.content).hexdigest()})
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code!=404: raise
            errors.append(str(exc))
        except (ValueError,KeyError,RuntimeError) as exc:
            errors.append(str(exc))
    raise ProviderMiss('PDB: no se encontró una cadena con identidad exacta y cobertura completa del rango. '+('; '.join(errors[-2:])))


def fetch_swiss_repository(fetcher, accession, residue_range):
    if '-' in accession: raise ProviderMiss('SWISS-MODEL Repository automático requiere accession canónico.')
    sequence=fetcher.sequence(accession); start,end=_range(sequence,residue_range)
    url=f'https://swissmodel.expasy.org/repository/uniprot/{accession}.json'
    data=fetcher._request('get',url,params={'provider':'swissmodel'},timeout=(10,60)).json()
    # No reutilizar un espejo AlphaFold ni una estructura PDB como otro método de generación.
    models=[m for m in data.get('result',{}).get('structures',[]) if str(m.get('provider','')).upper()=='SWISSMODEL'
            and int(m.get('from',0))<=start and int(m.get('to',0))>=end]
    models.sort(key=lambda m:float(m.get('gmqe') or 0),reverse=True)
    seen=set(); errors=[]
    for model in models:
        template=model.get('template','')
        if template in seen: continue
        seen.add(template)
        if len(seen)>5: break
        if not re.fullmatch(r'[0-9][A-Za-z0-9]{3}\.[0-9]+\.[A-Za-z0-9]+',template): continue
        origin=f'https://swissmodel.expasy.org/repository/uniprot/{accession}.pdb'
        params={'provider':'swissmodel','template':template,'range':f'{model["from"]}-{model["to"]}'}
        try:
            response=fetcher._request('get',origin,params=params,timeout=(10,90))
            # Los PDB de SMR vienen numerados por posición UniProt. Si no, rechazar sin adivinar.
            available=sorted({line[21] for line in response.text.splitlines() if line.startswith('ATOM  ')})
            for chain in available:
                if fetcher.chains and chain not in [c.strip() for c in fetcher.chains.split(',')]: continue
                lines=[line for line in response.text.splitlines() if line.startswith('ATOM  ') and line[21]==chain
                       and line[26:27].strip()=='' and start<=int(line[22:26])<=end]
                try:
                    return _write_checked(fetcher,accession,'swissmodel',lines,sequence,start,end,
                        {'structure_source':'SWISS-MODEL Repository','source':response.url,'source_entry':template+':'+chain,
                         'prediction_method':'Modelado por homología; modelo existente de SWISS-MODEL',
                         'quality_metrics':{'GMQE':model.get('gmqe'),'QMEAN.avg_local_score':model.get('qmean',{}).get('avg_local_score')},
                         'template':template,'model_created_at':model.get('created_date'),
                         'remote_structure_sha256':hashlib.sha256(response.content).hexdigest()})
                except ValueError as exc: errors.append(str(exc))
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code!=404: raise
            errors.append(str(exc))
    raise ProviderMiss('SWISS-MODEL Repository: no hay un modelo propio con identidad y cobertura completa. '+('; '.join(errors[-2:])))
