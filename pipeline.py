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
from preparation import prepare_protein

SCHEMA = ["tipo", "identificador", "nombre_comun", "categoria"]
CONTROL = {"tipo": "receptor", "identificador": "P02769", "nombre_comun": "Albumina_bovina_referencia", "categoria": "control"}
DUMMY = {"tipo": "receptor", "identificador": "PDB:1UBQ", "nombre_comun": "Ubiquitina_1UBQ", "categoria": "control"}


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_type(value: str) -> str:
    value = value.strip().lower()
    return "ligando" if value == "rbp" else value


def protein_key(item: dict) -> str:
    # Preservar las claves y hashes históricos para no duplicar envíos existentes.
    role = normalize_type(item["tipo"])
    storage_role = "RBP" if role == "ligando" else role
    return f"{storage_role}:{item['identificador'].upper()}"


def protein_label(item: dict) -> str:
    return f"{normalize_type(item['tipo'])}:{item['identificador'].upper()}"


def read_inputs(text: str) -> list:
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), skipinitialspace=True)
    if not reader.fieldnames or set(SCHEMA) - set(reader.fieldnames):
        raise ValueError("El CSV debe contener: " + ", ".join(SCHEMA))
    items, seen = [], {}
    for line, raw in enumerate(reader, 2):
        item = {key: (raw.get(key) or "").strip() for key in SCHEMA}
        if not any(item.values()):
            continue
        item["tipo"] = normalize_type(item["tipo"])
        item["categoria"] = item["categoria"].upper() if item["categoria"].lower() != "control" else "control"
        item["identificador"] = item["identificador"].upper()
        if item["tipo"] not in ("ligando", "receptor") or not item["identificador"]:
            raise ValueError(f"Fila {line}: usa tipo ligando o receptor y un identificador.")
        if item["tipo"] == "receptor" and item["categoria"] not in ("A", "B", "C", "control"):
            raise ValueError(f"Fila {line}: categoría de receptor debe ser A, B, C o control.")
        item["nombre_comun"] = item["nombre_comun"] or item["identificador"]
        start, end = (raw.get("residuo_inicio") or "").strip(), (raw.get("residuo_fin") or "").strip()
        if start or end:
            if not start.isdigit() or not end.isdigit() or not 1 <= int(start) <= int(end):
                raise ValueError(f"Fila {line}: indica residuo_inicio y residuo_fin como enteros positivos en orden.")
            item["residuo_inicio"], item["residuo_fin"] = int(start), int(end)
        chains = (raw.get('cadenas') or '').strip()
        if chains:
            item['cadenas'] = chains
        key = protein_key(item)
        if key in seen:
            if seen[key] != item:
                raise ValueError(f"Fila {line}: metadatos contradictorios para {key}.")
            continue
        seen[key] = item
        items.append(item)
    if not any(p["tipo"] == "ligando" for p in items) or not any(p["tipo"] == "receptor" and p["categoria"] != "control" for p in items):
        raise ValueError("Incluye al menos un ligando y un receptor candidato.")
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
    def create(cls, directory: Path, items: list, taxon: int, local: dict, dummy: bool, email: str, albumin: bool = True, region_mode='full'):
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / "pipeline_config.json").exists():
            raise ValueError("Este lote ya existe. Usa Abrir lote para reanudarlo o elige otra carpeta.")
        items = [{**item, "tipo": normalize_type(item["tipo"])} for item in items]
        # Las referencias opcionales no sustituyen controles experimentales del CSV.
        for control in ([CONTROL] if albumin else []) + ([DUMMY] if dummy else []):
            matches = [p for p in items if protein_key(p) == protein_key(control)]
            if matches and matches[0]["categoria"] != "control":
                raise ValueError(f"{control['identificador']} está definido como candidato; selecciona otro control en pipeline.py.")
            if not matches:
                items.append(dict(control))
        config = {"schema_version": 1, "created_at": now(), "taxon": int(taxon), "proteins": items,
                  "local_pdb": local, "email": email, "structures": {}, "errors": {}, "jobs": [], "results": {},
                  "optional_references": {"albumin": albumin, "ubiquitin": dummy},
                  'region_mode': region_mode,
                  "control_note": "La categoría control es una etiqueta; documentar su evidencia experimental para cada ligando."}
        instance = cls(directory, config)
        instance.save()
        return instance

    @classmethod
    def load(cls, directory: Path):
        path = Path(directory) / "pipeline_config.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("schema_version") != 1:
            raise ValueError("Versión de configuración no compatible.")
        for item in config["proteins"]:
            item["tipo"] = normalize_type(item["tipo"])
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
                if self.config.get('region_mode') == 'extracellular' and item.get('residuo_inicio') is None and not previous:
                    accession = fetcher.resolve(item['identificador'])
                    start, end = fetcher.extracellular_range(accession)
                    item.update(residuo_inicio=start, residuo_fin=end,
                                range_source=f'https://rest.uniprot.org/uniprotkb/{accession}.json')
                    self.save()
                if previous:
                    requested_range = [item["residuo_inicio"], item["residuo_fin"]] if item.get("residuo_inicio") is not None else None
                    if previous.get("residue_range") != requested_range:
                        raise ValueError("El rango de residuos cambió; crea otro lote para preservar los resultados anteriores.")
                    validate_pdb(Path(previous["path"]))
                    if sha256(Path(previous["path"])) != previous["sha256"]:
                        raise ValueError("El PDB cambió; crea otro lote para preservar resultados anteriores.")
                    self.config["errors"].pop(key, None)
                    continue
                callback({"kind": "message", "text": f"Estructura: {protein_label(item)}"})
                local = self.config["local_pdb"].get(key)
                if item["identificador"].startswith("PDB:") and not local:
                    result = fetcher.fetch_pdb(item["identificador"][4:])
                else:
                    if item.get("residuo_inicio") is not None:
                        result = fetcher.fetch(item["identificador"], local,
                                               residue_range=(item["residuo_inicio"], item["residuo_fin"]))
                    else:
                        result = fetcher.fetch(item["identificador"], local)
                self.config["structures"][key] = result
                self.config["errors"].pop(key, None)
            except Exception as exc:
                self.config["errors"][key] = str(exc)
                callback({"kind": "message", "text": f"ERROR {protein_label(item)}: {exc}"})
            self.save()
        self._prepare_docking_files(callback)
        self._build_jobs()
        self.save()

    def _prepare_docking_files(self, callback=lambda event: None):
        self.config.setdefault('docking_structures', {})
        for item in self.config['proteins']:
            key = protein_key(item)
            if key not in self.config['structures'] or key in self.config['errors']:
                continue
            # Nunca cambiar los PDB de un lote que ya generó pares históricos.
            if self.config['jobs'] and key not in self.config['docking_structures']:
                continue
            source = self.config['structures'][key]
            previous = self.config['docking_structures'].get(key)
            if previous:
                if previous['input_sha256'] != source['sha256'] or sha256(Path(previous['path'])) != previous['sha256']:
                    self.config['errors'][key] = 'La estructura preparada cambió. Crea otro lote.'
                continue
            try:
                target = self.directory / 'prepared' / (hashlib.sha256(key.encode()).hexdigest()[:8] + '_' + Path(source['path']).name)
                report = prepare_protein(Path(source['path']), target, item.get('cadenas', ''))
                if 'alphafold' in source.get('source', ''):
                    confidence = [float(line[60:66]) for line in Path(target).read_text().splitlines()
                                  if line.startswith('ATOM  ') and line[12:16].strip() == 'CA' and len(line) >= 66]
                    if confidence:
                        report['mean_plddt'] = sum(confidence) / len(confidence)
                        report['fraction_plddt_below_50'] = sum(v < 50 for v in confidence) / len(confidence)
                        if report['fraction_plddt_below_50'] > 0.2:
                            report['warnings'].append('Más del 20% de residuos tienen pLDDT < 50; revisar dominios y regiones desordenadas.')
                target.with_suffix('.preparation.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
                self.config['docking_structures'][key] = report
                for warning in report['warnings']:
                    callback({'kind': 'message', 'text': protein_label(item) + ': ' + warning})
            except Exception as exc:
                self.config['errors'][key] = str(exc)
                callback({'kind': 'message', 'text': f'No se pudo preparar {protein_label(item)}: {exc}'})

    def _build_jobs(self):
        ligands = [p for p in self.config["proteins"] if normalize_type(p["tipo"]) == "ligando"]
        receptors = [p for p in self.config["proteins"] if p["tipo"] == "receptor"]
        jobs, skipped = [], []
        for ligand in ligands:
            for receptor in receptors:
                lk, rk = protein_key(ligand), protein_key(receptor)
                structures = {**self.config['structures'], **self.config.get('docking_structures', {})}
                if lk not in structures or rk not in structures or lk in self.config["errors"] or rk in self.config["errors"]:
                    skipped.append({"Ligando": ligand["identificador"], "Receptor": receptor["identificador"],
                                    "motivo": "; ".join(self.config["errors"].get(k, "") for k in (lk, rk)) or "Estructura pendiente"})
                    continue
                identity = "|".join([lk, rk, structures[lk]["sha256"], structures[rk]["sha256"]])
                name = "dock_" + hashlib.sha256(identity.encode()).hexdigest()[:20]
                jobs.append({"receptor_pdb": structures[rk]["path"], "ligand_pdb": structures[lk]["path"],
                             "jobname": name, "email": self.config["email"], "Ligando": ligand["identificador"],
                             "Receptor": receptor["identificador"], "Categoria_Receptor": receptor["categoria"]})
        self.config["jobs"], self.config["skipped_pairs"] = jobs, skipped
        for filename, rows, fields in [
            ("jobs.csv", jobs, ["receptor_pdb", "ligand_pdb", "jobname", "email"]),
            ("pares_omitidos.csv", skipped, ["Ligando", "Receptor", "motivo"]),
        ]:
            with (self.directory / filename).open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)

    def verify_structures(self):
        for item in list(self.config["structures"].values()) + list(self.config.get('docking_structures', {}).values()):
            path = Path(item["path"])
            validate_pdb(path)
            if sha256(path) != item["sha256"]:
                raise ValueError(f"El PDB {path.name} cambió. Crea un lote nuevo.")

    def cloud_results(self):
        results = dict(self.config['results'])
        path = self.directory / 'monitor_state.json'
        if path.exists():
            try:
                state = json.loads(path.read_text(encoding='utf-8'))
                for name, result in state.get('results', {}).items():
                    if result.get('checked_at', '') >= results.get(name, {}).get('checked_at', ''):
                        results[name] = result
            except (ValueError, OSError):
                pass
        return results

    def collect(self, callback=lambda event: None, stop=None, download_count=0, persist=True):
        from model_files import download_models
        self.config['results'] = self.cloud_results()
        logs = latest_jobs(self.directory / "run-log.csv")
        known_names = {job["jobname"] for job in self.config["jobs"]}
        for name, row in logs.items():
            if stop and stop.is_set():
                break
            if name not in known_names or not accepted(row):
                continue
            previous = self.config["results"].get(name, {})
            cached = previous.get('models', [])
            if (previous.get("token") == row["token"] and previous.get("state") == "completado"
                    and len(cached) >= download_count and all(Path(m['raw_path']).exists() for m in cached)):
                continue
            result = {"token": row["token"], "score": None, "checked_at": now(), "error": ""}
            try:
                score, html = fetch_score(row["result_url"])
                reports = self.directory / "reports"
                reports.mkdir(exist_ok=True)
                (reports / f"{name}.html").write_text(html, encoding="utf-8")
                result.update(score=score, state="completado" if score is not None else "pendiente_o_formato_desconocido")
                if score is not None and download_count:
                    directory = self.directory / 'models' / name / hashlib.sha256(row['token'].encode()).hexdigest()[:16]
                    result['model_directory'] = str(directory.resolve())
                    try:
                        result['models'] = download_models(row['result_url'], html, directory, download_count)
                    except Exception as exc:
                        result['models'] = previous.get('models', []) if previous.get('token') == row['token'] else []
                        result['download_error'] = str(exc)
            except Exception as exc:
                result.update(state="error_consulta", error=str(exc))
            self.config["results"][name] = result
            if persist:
                self.save()
            callback({"kind": "message", "text": f"{name}: {result['state']} | score={result['score']}"})
            if result['state'] == 'completado' and (previous.get('token') != row['token'] or previous.get('state') != 'completado'):
                callback({'kind': 'result_ready', 'name': name, 'result': result})
            if stop and stop.wait(1):
                break

    def table(self, mode='server'):
        if mode == 'local':
            return summary(self.config['jobs'], self.directory / 'run-log.csv', self.config.get('local_results', {}), local=True)
        return summary(self.config["jobs"], self.directory / "run-log.csv", self.cloud_results())
