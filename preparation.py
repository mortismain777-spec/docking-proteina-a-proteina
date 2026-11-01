"""Preparación estructural conservadora y trazable para docking proteína–proteína."""
from __future__ import annotations

import json
import math
from pathlib import Path

from data_fetcher import sha256, validate_pdb

AMINO_ACIDS = set('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split())


def prepare_protein(source: Path, target: Path, chains: str = '') -> dict:
    """No añade residuos, protonación ni energía de minimización inventadas."""
    source, target = Path(source), Path(target)
    validate_pdb(source)
    allowed = {part.strip() for part in chains.split(',') if part.strip()}
    lines, warnings, removed = source.read_text(encoding='utf-8', errors='replace').splitlines(), [], 0
    records, first_model, in_model = [], None, True
    for line in lines:
        if line.startswith('MODEL'):
            if first_model is None:
                first_model = line
            else:
                warnings.append('Se utilizó sólo el primer modelo del conjunto estructural.')
                break
        if not line.startswith('ATOM  '):
            if line.startswith('HETATM'):
                removed += 1
            continue
        if allowed and line[21:22] not in allowed:
            removed += 1
            continue
        element = line[76:78].strip() if len(line) >= 78 else ''
        atom = line[12:16].strip().lstrip('0123456789')
        if element in ('H', 'D') or (not element and atom.startswith(('H', 'D'))):
            removed += 1
            continue
        if line[17:20] not in AMINO_ACIDS:
            warnings.append(f'Residuo no estándar {line[17:20]} {line[21:27].strip()}; requiere revisión.')
        records.append(line)
    found = {line[21:22] for line in records}
    if allowed - found:
        raise ValueError('No se encontraron las cadenas solicitadas: ' + ', '.join(sorted(allowed - found)))
    if not records or not any(line[12:16].strip() == 'CA' and line[17:20] in AMINO_ACIDS for line in records):
        raise ValueError('La selección no contiene una proteína con átomos CA reconocibles.')
    # Un conformero alternativo por residuo, compartiendo los átomos sin altloc.
    occupancy = {}
    for line in records:
        alt = line[16:17].strip()
        if alt:
            key = (line[21:27], alt)
            try:
                occupancy[key] = occupancy.get(key, 0) + float(line[54:60].strip() or 0)
            except ValueError:
                occupancy[key] = occupancy.get(key, 0)
    selected = {}
    for (residue, alt), value in sorted(occupancy.items()):
        if residue not in selected or value > selected[residue][1]:
            selected[residue] = (alt, value)
    atoms, seen = [], set()
    for line in records:
        alt, residue = line[16:17].strip(), line[21:27]
        if alt and selected[residue][0] != alt:
            removed += 1
            continue
        key = (residue, line[12:16])
        if key in seen:
            raise ValueError('Identificadores atómicos duplicados: selecciona cadenas inequívocas antes de preparar.')
        seen.add(key)
        atoms.append(line[:16] + ' ' + line[17:])
    by_residue = {}
    for line in atoms:
        by_residue.setdefault(line[21:27], set()).add(line[12:16].strip())
    missing = [key.strip() for key, names in by_residue.items() if not {'N', 'CA', 'C', 'O'} <= names]
    if missing:
        warnings.append(f'{len(missing)} residuos tienen esqueleto incompleto; revisar antes de interpretar poses.')
    coordinates = [[float(line[a:b]) for a, b in [(30,38), (38,46), (46,54)]] for line in atoms]
    minimum, maximum = [min(p[i] for p in coordinates) for i in range(3)], [max(p[i] for p in coordinates) for i in range(3)]
    center = [(a+b)/2 for a,b in zip(minimum, maximum)]
    size = [b-a for a,b in zip(minimum, maximum)]
    output, chain = [], None
    for line in atoms:
        if chain is not None and line[21] != chain:
            output.append('TER')
        chain = line[21]
        output.append(line)
    output.extend(['TER', 'END'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(output) + '\n', encoding='utf-8')
    validate_pdb(target)
    report = {'path': str(target.resolve()), 'sha256': sha256(target), 'input_sha256': sha256(source),
              'atoms': len(atoms), 'residues': len(by_residue), 'chains': sorted(found), 'removed_atoms': removed,
              'warnings': sorted(set(warnings)), 'bounding_center_A': center, 'bounding_size_A': size,
              'search': 'Global, sin caja manual. Las dimensiones describen la proteína, no restringen el motor.',
              'method': 'Átomos pesados; primer modelo; selección de cadenas; altloc por ocupación; sin aguas/HETATM. Sin reconstrucción, minimización ni glicanos.'}
    target.with_suffix('.preparation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report
