"""Motor HDOCKlite global: Linux nativo o WSL; resultados locales separados."""
from __future__ import annotations

import json
import math
import os
import platform
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from data_fetcher import sha256, validate_pdb
from model_files import viewer_copy, viewer_scripts
from preparation import prepare_protein


def native_scores(path: Path) -> list:
    scores = []
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        fields = line.split()
        if len(fields) != 10:
            continue
        try:
            numbers = [float(value) for value in fields]
            if all(math.isfinite(n) for n in numbers):
                scores.append(numbers[6])
        except ValueError:
            pass
    if not scores:
        raise ValueError('HDOCKlite no produjo soluciones numéricas reconocibles.')
    return scores


def split_models(source: Path, directory: Path, count: int) -> list:
    """Separa la salida multiMODEL de createpl sin modificar sus coordenadas."""
    groups, current, headers = [], [], []
    for line in Path(source).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('MODEL'):
            if current:
                groups.append(current)
            current = []
        elif line.startswith('ENDMDL'):
            if current:
                groups.append(current)
                current = []
        elif line.startswith(('ATOM  ', 'HETATM', 'TER')):
            current.append(line)
        elif line.startswith('REMARK') and not groups and not current:
            headers.append(line)
    if current:
        groups.append(current)
    if not groups:
        raise ValueError('createpl no generó modelos estructurales.')
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for rank, group in enumerate(groups[:count], 1):
        raw = directory / f'modelo_{rank}.pdb'
        raw.write_text('\n'.join(headers + group + ['END']) + '\n', encoding='utf-8')
        validate_pdb(raw)
        visual = directory / f'modelo_{rank}_visor.pdb'
        records.append({'rank': rank, 'raw_path': str(raw.resolve()), 'raw_sha256': sha256(raw),
                        'viewer': viewer_copy(raw, visual)})
    viewer_scripts(directory, [r['viewer']['path'] for r in records])
    (directory / 'modelos.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    return records


class LocalEngine:
    def __init__(self, tool_directory: str, distribution: str = '', callback=lambda event: None):
        self.tool_directory, self.distribution = tool_directory.strip(), distribution.strip()
        self.callback = callback
        self.stop_event = threading.Event()
        self.use_wsl = os.name == 'nt'

    def stop(self):
        self.stop_event.set()

    def prefix(self):
        if not self.use_wsl:
            return []
        return ['wsl.exe'] + (['--distribution', self.distribution] if self.distribution else []) + ['--exec']

    def path(self, value) -> str:
        value = str(value)
        if not self.use_wsl:
            return str(Path(value).expanduser().resolve())
        if value.startswith('/'):
            return value
        result = subprocess.run(self.prefix() + ['wslpath', '-a', '-u', str(Path(value).resolve())],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('WSL no está listo o no pudo convertir la ruta: ' + result.stderr[-500:])
        return result.stdout.strip()

    def executable(self, name):
        return self.path(self.tool_directory.rstrip('/\\') + '/' + name)

    def check(self) -> dict:
        if self.use_wsl:
            if not shutil.which('wsl.exe'):
                raise RuntimeError('Falta WSL. Instálalo con el asistente de Microsoft y reinicia si se solicita.')
            probe = subprocess.run(self.prefix() + ['uname', '-m'], capture_output=True, timeout=30,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if probe.returncode:
                raise RuntimeError('WSL/Ubuntu no está inicializado. Completa la instalación y el primer inicio de Ubuntu.')
        for name in ('hdock', 'createpl'):
            executable = self.executable(name)
            command = self.prefix() + (['test', '-x', executable] if self.use_wsl else ['test', '-x', executable])
            probe = subprocess.run(command, capture_output=True, timeout=15,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if probe.returncode:
                raise RuntimeError(f'No se puede ejecutar {name}. Comprueba la carpeta del motor y sus permisos en Linux.')
        return {'platform': 'WSL' if self.use_wsl else platform.system(), 'tools': self.tool_directory,
                'distribution': self.distribution, 'search': 'global_ab_initio'}

    def _run(self, command: list, console: Path):
        self.callback({'kind': 'message', 'text': 'Calculando en el equipo: ' + Path(console).parent.name})
        with console.open('w', encoding='utf-8') as handle:
            process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            code = process.wait()
        if code:
            raise RuntimeError(f'El motor local terminó con código {code}. Revisa {console}.')

    def run(self, jobs: list, output: Path, results: dict, count=5, save=lambda: None):
        self.check()
        output = Path(output)
        for job in jobs:
            if self.stop_event.is_set():
                break
            name = job['jobname']
            if results.get(name, {}).get('state') == 'completado':
                continue
            timestamp = datetime.now(timezone.utc).isoformat()
            directory = output / 'local' / name / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            directory.mkdir(parents=True, exist_ok=True)
            result = {'checked_at': timestamp, 'engine': 'HDOCKlite global', 'score': None, 'models': []}
            try:
                receptor = directory / 'inputs/receptor.pdb'
                ligand = directory / 'inputs/ligando.pdb'
                receptor_report = prepare_protein(Path(job['receptor_pdb']), receptor)
                ligand_report = prepare_protein(Path(job['ligand_pdb']), ligand)
                hdock_out = directory / 'hdock.out'
                combined = directory / 'complejos.pdb'
                command = self.prefix() + [self.executable('hdock'), self.path(receptor),
                                          self.path(ligand), '-out', self.path(hdock_out)]
                manifest = {'command': command, 'search': 'global_ab_initio',
                            'receptor_sha256': receptor_report['sha256'],
                            'ligand_sha256': ligand_report['sha256'], 'started_at': timestamp,
                            'preparation_warnings': receptor_report['warnings'] + ligand_report['warnings']}
                (directory / 'ejecucion.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                self._run(command, directory / 'hdock.log')
                scores = native_scores(hdock_out)
                self._run(self.prefix() + [self.executable('createpl'), self.path(hdock_out), self.path(combined),
                                          '-nmax', str(count), '-complex', '-models'], directory / 'createpl.log')
                if combined.exists():
                    models = split_models(combined, directory / 'modelos', count)
                else:
                    # Algunas versiones de createpl generan un PDB separado por pose.
                    files = sorted(directory.glob('complejos*'), key=lambda p: [int(n) if n.isdigit() else n for n in re.split(r'(\d+)', p.name)])
                    pieces = []
                    for rank, path in enumerate([p for p in files if p.is_file()][:count], 1):
                        validate_pdb(path)
                        pieces.extend(['MODEL ' + str(rank), path.read_text(encoding='utf-8'), 'ENDMDL'])
                    combined.write_text('\n'.join(pieces), encoding='utf-8')
                    models = split_models(combined, directory / 'modelos', count)
                for index, model in enumerate(models):
                    model['score'] = scores[index] if index < len(scores) else None
                result.update(state='completado', score=min(scores), models=models,
                              model_directory=str((directory / 'modelos').resolve()), error='')
            except Exception as exc:
                result.update(state='error_local', error=str(exc))
            results[name] = result
            save()
            self.callback({'kind': 'local_job', 'name': name, 'result': result})
