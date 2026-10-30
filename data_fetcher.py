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
        if not re.fullmatch(r"[A-Z0-9_.-]+", identifier):
            raise ValueError("Usa un accession UniProt o un símbolo de gen, sin espacios.")
        query = f"gene_exact:{identifier} AND organism_id:{self.taxon}"
        # Priorizar la entrada curada; usar no curadas sólo si no hay ninguna curada.
        for expression in (query + " AND reviewed:true", query):
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

    def fetch(self, identifier: str, local: Optional[str] = None) -> dict:
        key = hashlib.sha256(identifier.upper().encode()).hexdigest()[:12]
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
            if len(models) != 1:
                raise ValueError(f"{identifier}: {len(models)} modelos; asigna un PDB local para seleccionar la estructura.")
            origin = models[0]["pdbUrl"]
            self._download(origin, target)
        validate_pdb(target)
        return {"path": str(target.resolve()), "sha256": sha256(target), "source": origin, "uniprot": accession}

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
