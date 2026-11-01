"""Descarga de modelos y copias con cadenas diferenciadas para visores."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from data_fetcher import session, sha256, validate_pdb


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)


def viewer_copy(source: Path, target: Path) -> dict:
    """Distingue segmentos separados por TER; conserva exactamente coordenadas."""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    out, mapping, segment, previous, has_atoms = [], [], 0, None, False
    for line in Path(source).read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('MODEL'):
            segment, previous, has_atoms = 0, None, False
        if line.startswith(('ATOM  ', 'HETATM')):
            original = line[21:22]
            if has_atoms and previous is not None and original != previous:
                segment += 1
                has_atoms = False
            if segment >= len(alphabet):
                raise ValueError('Demasiados segmentos para una copia en formato PDB.')
            if not has_atoms:
                mapping.append({'original': original, 'viewer_chain': alphabet[segment]})
            previous, has_atoms = original, True
            line = line[:21] + alphabet[segment] + line[22:]
        elif line.startswith('TER') and has_atoms:
            segment += 1
            previous, has_atoms = None, False
        if line.startswith('REMARK') and not line[7:10].strip().isdigit():
            line = 'REMARK 999 ' + line[6:].strip()
        out.append(line)
    Path(target).write_text('\n'.join(out) + '\n', encoding='utf-8')
    validate_pdb(Path(target))
    return {'path': str(Path(target).resolve()), 'sha256': sha256(Path(target)), 'chains': mapping}


def viewer_scripts(directory: Path, paths: list) -> None:
    # Rutas relativas controladas: las sesiones se pueden abrir tras mover la carpeta.
    names = [Path(path).name for path in paths]
    (directory / 'abrir_chimerax.cxc').write_text('\n'.join(f'open "{name}"' for name in names) + '\ncolor bychain\nview\n', encoding='utf-8')
    (directory / 'abrir_pymol.pml').write_text('\n'.join(f'load "{name}", modelo_{i}' for i, name in enumerate(names, 1)) + '\nutil.cbc()\nzoom\n', encoding='utf-8')


def download_models(base_url: str, html: str, directory: Path, count: int = 5, client=None) -> list:
    if not 1 <= count <= 20:
        raise ValueError('Selecciona entre 1 y 20 modelos por par.')
    base = urlparse(base_url)
    if base.scheme not in ('http', 'https') or base.hostname != 'hdock.phys.hust.edu.cn' or not re.fullmatch(r'/data/[A-Za-z0-9_-]+/', base.path):
        raise ValueError('URL de trabajo HDOCK inválida para descargar modelos.')
    parser = Links()
    parser.feed(html)
    urls = {}
    for href in parser.links:
        url = urlparse(urljoin(base_url, href))
        match = re.fullmatch(re.escape(base.path) + r'model_([1-9][0-9]*)\.pdb', url.path)
        if match and url.hostname == base.hostname and url.scheme in ('http', 'https') and not url.username:
            urls[int(match[1])] = url.geturl()
    ranks = sorted(urls)[:count]
    if len(ranks) < count:
        raise ValueError(f'La página ofrece {len(ranks)} modelos descargables; se solicitaron {count}.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    client = client or session()
    records = []
    for rank in ranks:
        target = directory / f'modelo_{rank}.pdb'
        temporary = directory / (target.name + '.' + uuid.uuid4().hex + '.part')
        if not target.exists():
            response = client.get(urls[rank], timeout=(10, 60), allow_redirects=False)
            response.raise_for_status()
            if 300 <= response.status_code < 400 or len(response.content) > 50_000_000:
                raise ValueError('Descarga redirigida o archivo de modelo demasiado grande.')
            try:
                temporary.write_bytes(response.content)
                validate_pdb(temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        validate_pdb(target)
        visual = directory / f'modelo_{rank}_visor.pdb'
        viewed = viewer_copy(target, visual)
        records.append({'rank': rank, 'source': urls[rank], 'raw_path': str(target.resolve()),
                        'raw_sha256': sha256(target), 'viewer': viewed})
    (directory / 'modelos.json').write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding='utf-8')
    viewer_scripts(directory, [r['viewer']['path'] for r in records])
    return records
