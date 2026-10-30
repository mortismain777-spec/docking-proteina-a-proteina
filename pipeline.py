"""Configuración persistente y matriz reproducible de pares dirigidos."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from data_fetcher import StructureFetcher, sha256, validate_pdb
from job_runner import accepted, latest_jobs
from results_parser import fetch_score, summary

SCHEMA = ["tipo", "identificador", "nombre_comun", "categoria"]
CONTROL = {"tipo": "receptor", "identificador": "P02769", "nombre_comun": "Albumina_bovina_referencia", "categoria": "control"}
DUMMY = {"tipo": "receptor", "identificador": "PDB:1UBQ", "nombre_comun": "Ubiquitina_1UBQ", "categoria": "control"}


def now():
    return datetime.now(timezone.utc).isoformat()


def protein_key(item: dict) -> str:
    return f"{item['tipo']}:{item['identificador'].upper()}"


def read_inputs(text: str) -> list:
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), skipinitialspace=True)
    if not reader.fieldnames or set(SCHEMA) - set(reader.fieldnames):
        raise ValueError("El CSV debe contener: " + ", ".join(SCHEMA))
    items, seen = [], {}
    for line, raw in enumerate(reader, 2):
        item = {key: (raw.get(key) or "").strip() for key in SCHEMA}
        if not any(item.values()):
            continue
        item["tipo"] = "RBP" if item["tipo"].upper() == "RBP" else item["tipo"].lower()
        item["categoria"] = item["categoria"].upper() if item["categoria"].lower() != "control" else "control"
        item["identificador"] = item["identificador"].upper()
        if item["tipo"] not in ("RBP", "receptor") or not item["identificador"]:
            raise ValueError(f"Fila {line}: tipo o identificador inválido.")
        if item["tipo"] == "receptor" and item["categoria"] not in ("A", "B", "C", "control"):
            raise ValueError(f"Fila {line}: categoría de receptor debe ser A, B, C o control.")
        item["nombre_comun"] = item["nombre_comun"] or item["identificador"]
        key = protein_key(item)
        if key in seen:
            if seen[key] != item:
                raise ValueError(f"Fila {line}: metadatos contradictorios para {key}.")
            continue
        seen[key] = item
        items.append(item)
    if not any(p["tipo"] == "RBP" for p in items) or not any(p["tipo"] == "receptor" and p["categoria"] != "control" for p in items):
        raise ValueError("Incluye al menos una RBP y un receptor candidato.")
    return items


def write_json(path: Path, value):
    # Reemplazo atómico para no truncar la configuración si se interrumpe el programa.
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


class Pipeline:
    def __init__(self, directory: Path, config: dict):
        self.directory, self.config = Path(directory), config

    @classmethod
    def create(cls, directory: Path, items: list, taxon: int, local: dict, dummy: bool, email: str):
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / "pipeline_config.json").exists():
            raise ValueError("Este lote ya existe. Usa Abrir lote para reanudarlo o elige otra carpeta.")
        items = [dict(item) for item in items]
        # Mantener un control independiente por defecto, aunque existan controles personalizados.
        for control in [CONTROL] + ([DUMMY] if dummy else []):
            matches = [p for p in items if protein_key(p) == protein_key(control)]
            if matches and matches[0]["categoria"] != "control":
                raise ValueError(f"{control['identificador']} está definido como candidato; selecciona otro control en pipeline.py.")
            if not matches:
                items.append(dict(control))
        config = {"schema_version": 1, "created_at": now(), "taxon": int(taxon), "proteins": items,
                  "local_pdb": local, "email": email, "structures": {}, "errors": {}, "jobs": [], "results": {},
                  "control_note": "Controles de referencia provisionales; validar ausencia de interacción para cada RBP."}
        instance = cls(directory, config)
        instance.save()
        return instance

    @classmethod
    def load(cls, directory: Path):
        path = Path(directory) / "pipeline_config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("schema_version") != 1:
            raise ValueError("Versión de configuración no compatible.")
        return cls(path.parent.resolve(), config)

    def save(self):
        self.config["updated_at"] = now()
        write_json(self.directory / "pipeline_config.json", self.config)

    def prepare(self, callback=lambda event: None, stop=None):
        fetcher = StructureFetcher(self.directory / "structures", self.config["taxon"])
        for item in self.config["proteins"]:
            if stop and stop.is_set():
                break
            key = protein_key(item)
            previous = self.config["structures"].get(key)
            try:
                if previous:
                    validate_pdb(Path(previous["path"]))
                    if sha256(Path(previous["path"])) != previous["sha256"]:
                        raise ValueError("El PDB cambió; crea otro lote para preservar resultados anteriores.")
                    self.config["errors"].pop(key, None)
                    continue
                callback({"kind": "message", "text": f"Estructura: {key}"})
                local = self.config["local_pdb"].get(key)
                if item["identificador"].startswith("PDB:") and not local:
                    result = fetcher.fetch_pdb(item["identificador"][4:])
                else:
                    result = fetcher.fetch(item["identificador"], local)
                self.config["structures"][key] = result
                self.config["errors"].pop(key, None)
            except Exception as exc:
                self.config["errors"][key] = str(exc)
                callback({"kind": "message", "text": f"ERROR {key}: {exc}"})
            self.save()
        self._build_jobs()
        self.save()

    def _build_jobs(self):
        ligands = [p for p in self.config["proteins"] if p["tipo"] == "RBP"]
        receptors = [p for p in self.config["proteins"] if p["tipo"] == "receptor"]
        jobs, skipped = [], []
        for ligand in ligands:
            for receptor in receptors:
                lk, rk = protein_key(ligand), protein_key(receptor)
                structures = self.config["structures"]
                if lk not in structures or rk not in structures or lk in self.config["errors"] or rk in self.config["errors"]:
                    skipped.append({"RBP": ligand["identificador"], "Receptor": receptor["identificador"],
                                    "motivo": "; ".join(self.config["errors"].get(k, "") for k in (lk, rk)) or "Estructura pendiente"})
                    continue
                identity = "|".join([lk, rk, structures[lk]["sha256"], structures[rk]["sha256"]])
                name = "dock_" + hashlib.sha256(identity.encode()).hexdigest()[:20]
                jobs.append({"receptor_pdb": structures[rk]["path"], "ligand_pdb": structures[lk]["path"],
                             "jobname": name, "email": self.config["email"], "RBP": ligand["identificador"],
                             "Receptor": receptor["identificador"], "Categoria_Receptor": receptor["categoria"]})
        self.config["jobs"], self.config["skipped_pairs"] = jobs, skipped
        for filename, rows, fields in [
            ("jobs.csv", jobs, ["receptor_pdb", "ligand_pdb", "jobname", "email"]),
            ("pares_omitidos.csv", skipped, ["RBP", "Receptor", "motivo"]),
        ]:
            with (self.directory / filename).open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

    def verify_structures(self):
        for item in self.config["structures"].values():
            path = Path(item["path"])
            validate_pdb(path)
            if sha256(path) != item["sha256"]:
                raise ValueError(f"El PDB {path.name} cambió. Crea un lote nuevo.")

    def collect(self, callback=lambda event: None, stop=None):
        logs = latest_jobs(self.directory / "run-log.csv")
        known_names = {job["jobname"] for job in self.config["jobs"]}
        for name, row in logs.items():
            if stop and stop.is_set():
                break
            if name not in known_names or not accepted(row):
                continue
            previous = self.config["results"].get(name, {})
            if previous.get("token") == row["token"] and previous.get("state") == "completado":
                continue
            result = {"token": row["token"], "score": None, "checked_at": now(), "error": ""}
            try:
                score, html = fetch_score(row["result_url"])
                reports = self.directory / "reports"
                reports.mkdir(exist_ok=True)
                (reports / f"{name}.html").write_text(html, encoding="utf-8")
                result.update(score=score, state="completado" if score is not None else "pendiente_o_formato_desconocido")
            except Exception as exc:
                result.update(state="error_consulta", error=str(exc))
            self.config["results"][name] = result
            self.save()
            callback({"kind": "message", "text": f"{name}: {result['state']} | score={result['score']}"})
            if stop and stop.wait(1):
                break

    def table(self):
        return summary(self.config["jobs"], self.directory / "run-log.csv", self.config["results"])
