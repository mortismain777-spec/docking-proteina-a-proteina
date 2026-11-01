"""Identificadores y estructuras; ninguna llamada envía trabajos a HDOCK."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ACCESSION = re.compile(r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-\d+)?$")


def session() -> requests.Session:
    """Reintentos limitados sólo para consultas idempotentes."""
    client = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    client.mount("https://", HTTPAdapter(max_retries=retry))
    client.headers["User-Agent"] = "DockingMatrix/0.1 (research desktop client)"
    return client


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_pdb(path: Path) -> None:
    """Comprobación de formato mínima; no sustituye preparación estructural."""
    text = path.read_text(encoding="utf-8", errors="replace")
    atoms = [line for line in text.splitlines() if line.startswith("ATOM  ")]
    if not atoms:
        raise ValueError(f"{path.name}: no contiene registros ATOM de proteína.")
    for line in atoms:
        try:
            xyz = [float(line[a:b]) for a, b in [(30, 38), (38, 46), (46, 54)]]
            if not all(__import__('math').isfinite(v) for v in xyz):
                raise ValueError()
        except ValueError:
            raise ValueError(f"{path.name}: coordenadas ATOM inválidas.") from None


class StructureFetcher:
    def __init__(self, directory: Path, taxon: int = 9606, client=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.taxon = int(taxon)
        self.client = client or session()

    def resolve(self, identifier: str) -> str:
        identifier = identifier.strip().upper()
        if ACCESSION.fullmatch(identifier):
            return identifier
        if len(identifier) > 150 or not re.fullmatch(r"[\w .()/-]+", identifier):
            raise ValueError("Usa un accession, símbolo de gen o nombre de proteína, sin comillas ni operadores de búsqueda.")
        queries = []
        if re.fullmatch(r'[A-Z0-9_.-]+', identifier):
            queries.append(f'gene_exact:{identifier} AND organism_id:{self.taxon}')
        queries.append(f'protein_name:"{identifier}" AND organism_id:{self.taxon}')
        expressions = [expr for query in queries for expr in (query + ' AND reviewed:true', query)]
        for expression in expressions:
            response = self.client.get("https://rest.uniprot.org/uniprotkb/search", params={
                "query": expression, "format": "json", "size": 2,
                "fields": "accession,gene_names,organism_id",
            }, timeout=(10, 45))
            response.raise_for_status()
            hits = response.json().get("results", [])
            if hits:
                break
        if len(hits) != 1:
            raise ValueError(f"{identifier}: {len(hits)} o más coincidencias; especifica UniProt ID y comprueba el organismo.")
        return hits[0]["primaryAccession"]

    def extracellular_range(self, accession: str) -> tuple:
        response = self.client.get(f'https://rest.uniprot.org/uniprotkb/{accession}.json', timeout=(10,45))
        response.raise_for_status()
        domains = [f for f in response.json().get('features', [])
                   if f.get('type') == 'Topological domain' and f.get('description', '').lower() == 'extracellular']
        if len(domains) != 1:
            raise ValueError('No hay una única región extracelular anotada. Usa estructura completa o un rango explícito.')
        location = domains[0]['location']
        if any(location[end].get('modifier', 'EXACT') != 'EXACT' for end in ('start','end')):
            raise ValueError('Los límites extracelulares son inciertos; selecciona un rango explícito.')
        return int(location['start']['value']), int(location['end']['value'])

    def fetch(self, identifier: str, local: Optional[str] = None, residue_range=None) -> dict:
        identity = identifier.upper() + (f":{residue_range[0]}-{residue_range[1]}" if residue_range else "")
        key = hashlib.sha256(identity.encode()).hexdigest()[:12]
        target = self.directory / f"{key}.pdb"
        if local:
            source = Path(local).expanduser().resolve()
            validate_pdb(source)
            if source != target.resolve():
                shutil.copyfile(source, target)
            origin, accession = str(source), ""
        else:
            accession = self.resolve(identifier)
            response = self.client.get(f"https://alphafold.ebi.ac.uk/api/prediction/{accession}", timeout=(10, 45))
            response.raise_for_status()
            predictions = response.json()
            # No elegir silenciosamente un fragmento entre varios modelos.
            models = [item for item in predictions if item.get("pdbUrl")]
            # La API puede devolver además isoformas: escoger sólo el accession pedido.
            exact = [item for item in models if item.get("uniprotAccession") == accession]
            if any(item.get("uniprotAccession") for item in models):
                models = exact
            if len(models) != 1:
                raise ValueError(f"{identifier}: {len(models)} modelos; asigna un PDB local para seleccionar la estructura.")
            if residue_range and models[0].get("uniprotStart", 1) != 1:
                raise ValueError("El modelo es un fragmento: revisa su numeración antes de recortar residuos.")
            origin = models[0]["pdbUrl"]
            self._download(origin, target)
        validate_pdb(target)
        metadata = {"source": origin, "uniprot": accession}
        if residue_range:
            start, end = residue_range
            if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end):
                raise ValueError("Rango de residuos inválido.")
            metadata["full_structure_sha256"] = sha256(target)
            lines = target.read_text(encoding="utf-8").splitlines()
            atoms = [line for line in lines if line.startswith("ATOM  ") and start <= int(line[22:26]) <= end]
            if len({line[21] for line in atoms}) != 1 or any(line[26:27].strip() for line in atoms):
                raise ValueError("El recorte exige una sola cadena con numeración de residuos sin inserciones.")
            positions = {int(line[22:26]) for line in atoms}
            if positions != set(range(start, end + 1)):
                raise ValueError("La estructura no cubre completamente el rango solicitado; revisa la numeración.")
            target.write_text("\n".join(atoms + ["TER", "END"]) + "\n", encoding="utf-8")
            validate_pdb(target)
            metadata["residue_range"] = [start, end]
            metadata["preparation"] = "Recorte por numeración PDB; sin alterar coordenadas ni añadir glicanos."
        return {"path": str(target.resolve()), "sha256": sha256(target), **metadata}

    def fetch_pdb(self, code: str) -> dict:
        if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", code):
            raise ValueError("Código PDB inválido")
        target = self.directory / f"{code.upper()}.pdb"
        origin = f"https://files.rcsb.org/download/{code.upper()}.pdb"
        self._download(origin, target)
        return {"path": str(target.resolve()), "sha256": sha256(target), "source": origin, "uniprot": ""}

    def _download(self, url: str, target: Path) -> None:
        response = self.client.get(url, timeout=(10, 60))
        response.raise_for_status()
        temporary = target.with_suffix(".part")
        try:
            temporary.write_bytes(response.content)
            validate_pdb(temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
