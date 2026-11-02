"""Caché validada y reportes de estructuras; no contiene lógica de docking."""
from __future__ import annotations
import csv
import hashlib
import json
import math
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

APP_VERSION = '0.4.0'
AA = dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),
              'ARNDCQEGHILKMFPSTWYV'))


def digest(value):
    return hashlib.sha256(value).hexdigest()


def pdb_info(path, method='', expected_sequence=None):
    """Un Cα por residuo; B-factor sólo representa confianza en modelos conocidos."""
    residues, confidence, models = {}, [], 0
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('MODEL'):
            models += 1
            if models > 1:
                raise ValueError('Se requiere un único modelo por estructura.')
        if not line.startswith('ATOM  '):
            continue
        try:
            if not all(math.isfinite(float(line[a:b])) for a,b in ((30,38),(38,46),(46,54))):
                raise ValueError()
            int(line[22:26])
        except (ValueError, IndexError):
            raise ValueError('Coordenadas o numeración ATOM inválidas.') from None
        if line[12:16].strip() != 'CA':
            continue
        key = (line[21], line[22:27])
        if key in residues:
            continue
        residues[key] = AA.get(line[17:20], 'X')
        if method in ('AlphaFold', 'ESMFold'):
            try:
                value = float(line[60:66])
                confidence.append(value if math.isfinite(value) and 0 <= value <= 100 else None)
            except ValueError:
                confidence.append(None)
    if not residues:
        raise ValueError('El PDB no contiene residuos de proteína con Cα.')
    sequence = ''.join(residues.values())
    if expected_sequence is not None and sequence != expected_sequence:
        raise ValueError('La secuencia del PDB no coincide exactamente con la enviada a ESMFold.')
    valid_confidence = confidence and all(v is not None for v in confidence)
    scale = '0-100'
    # El endpoint público probado devuelve la escala histórica 0–1 de ESMFold.
    # Registrar la inferencia; conservar los B-factors originales en el PDB.
    if valid_confidence and method == 'ESMFold' and max(confidence) <= 1:
        confidence = [100*v for v in confidence]
        scale = '0-1 (inferida para ESMFold; métricas multiplicadas por 100)'
    return {'sequence': sequence, 'sequence_sha256': digest(sequence.encode()),
            'residue_count': len(residues), 'chains': sorted({k[0] for k in residues}),
            'confidence_input_scale': scale if valid_confidence else None,
            'mean_plddt': sum(confidence)/len(confidence) if valid_confidence else None,
            'pct_plddt_below_50': 100*sum(v < 50 for v in confidence)/len(confidence) if valid_confidence else None}


class StructureCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def find(self, identifier, taxon, residue_range, chains, allow_fallback, provider_order=None):
        """Los sidecars son el índice offline; nunca inferir procedencia por el nombre."""
        candidates = []
        for sidecar in self.directory.glob('*.json'):
            try:
                data = json.loads(sidecar.read_text(encoding='utf-8'))
                if data.get('cache_schema') != 1 or data['taxon'] != taxon:
                    continue
                if identifier.upper() not in (data['identifier'].upper(), data.get('accession', '').upper()):
                    continue
                if data['requested_range'] != (list(residue_range) if residue_range else None) or data['requested_chains'] != chains:
                    continue
                method = data['metadata']['structure_source']
                if provider_order is not None:
                    from provider_settings import METHOD_PROVIDER
                    provider=data['metadata'].get('provider_id',METHOD_PROVIDER.get(method))
                    if provider not in provider_order: continue
                    rank=provider_order.index(provider)
                else:
                    if method not in (('AlphaFold', 'ESMFold') if allow_fallback else ('AlphaFold',)): continue
                    rank=method!='AlphaFold'
                path = sidecar.with_suffix('.pdb')
                if digest(path.read_bytes()) != data['pdb_sha256']:
                    continue
                info = pdb_info(path, method)
                if info['sequence_sha256'] != data['sequence_sha256']:
                    continue
                candidates.append((rank, sidecar, path, data))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        if not candidates:
            return None
        _, _, path, data = sorted(candidates, key=lambda c:(c[0],str(c[1])))[0]
        info=pdb_info(path,data['metadata']['structure_source'])
        return path, {**data['metadata'],**{k:v for k,v in info.items() if k!='sequence'}}

    def store(self, path, metadata, identifier, accession, taxon, residue_range, chains):
        info = pdb_info(path, metadata['structure_source'])
        identity = {'identifier': identifier, 'accession': accession, 'taxon': taxon,
                    'requested_range': list(residue_range) if residue_range else None,
                    'requested_chains': chains, 'sequence_sha256': info['sequence_sha256'],
                    'method': metadata['structure_source']}
        key = digest(json.dumps(identity, sort_keys=True).encode())
        target = self.directory / (key + '.pdb')
        temporary = target.with_name(uuid.uuid4().hex + '.tmp')
        try:
            shutil.copyfile(path, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        data = {**identity, 'cache_schema': 1, 'pdb_sha256': digest(target.read_bytes()),
                'created_at': datetime.now(timezone.utc).isoformat(), 'metadata': metadata}
        tmp = target.with_name(uuid.uuid4().hex + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(target.with_suffix('.json'))


def write_structure_reports(directory, proteins, structures, errors, key_function, attempts=None):
    fields = ['identificador_entrada','accession_resuelto','tipo','fuente_estructura','pLDDT_medio',
              'pct_residuos_pLDDT_bajo','rango_usado','sha256_pdb','ruta_pdb','estado','detalle','cache_hit',
              'metodo_generacion','entrada_origen','metricas_calidad','intentos_proveedor']
    rows, manual = [], []
    for item in proteins:
        key = key_function(item)
        model, error = structures.get(key, {}), errors.get(key, '')
        state = model.get('structure_status', 'OK') if model else ('NEEDS_MANUAL' if error else 'PENDING')
        if error:
            state = model.get('error_status', 'FAILED') if model else ('RETRY_PENDING' if error.startswith('RETRY_PENDING:') else 'NEEDS_MANUAL')
            if error.startswith('INPUT_ERROR:'):
                state='INPUT_ERROR'
        row = dict(zip(fields[:12], [item['identificador'],model.get('resolved_accession',model.get('uniprot','')),
            item['tipo'],model.get('structure_source','Desconocida'),model.get('mean_plddt'),model.get('pct_plddt_below_50'),
            model.get('residue_range',''),model.get('sha256',''),model.get('path',''),state,error,model.get('cache_hit',False)]))
        row.update(metodo_generacion=model.get('prediction_method',''),entrada_origen=model.get('source_entry',model.get('source','')),
                   metricas_calidad=json.dumps(model.get('quality_metrics',{}),ensure_ascii=False),
                   intentos_proveedor=json.dumps(model.get('provider_attempts',(attempts or {}).get(key,[])),ensure_ascii=False))
        rows.append(row)
        if error:
            manual.append(f'{key}\t{state}\t{error}')
    directory = Path(directory)
    with (directory/'structure_report.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle,fieldnames=fields)
        writer.writeheader()
        # Evitar que identificadores o rutas se interpreten como fórmulas en Excel.
        writer.writerows({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else ('NA' if v is None else v)) for k,v in row.items()} for row in rows)
    (directory/'needs_manual_modeling.txt').write_text('\n'.join(manual)+ ('\n' if manual else ''),encoding='utf-8')
    return rows
