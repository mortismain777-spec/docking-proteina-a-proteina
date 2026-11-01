"""Adaptador de hdock_batch: subprocesos aislados, bitácoras y reanudación."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

LOG_FIELDS = ["row", "timestamp", "jobname", "token", "result_url", "ok", "error"]


def read_log(path: Path) -> list:
    """Tolera encabezados repetidos del upstream y una última fila incompleta."""
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return [r for r in csv.DictReader(handle) if r.get("jobname") not in (None, "", "jobname")]


def accepted(row: dict) -> bool:
    parsed = urlparse(row.get("result_url", ""))
    return (str(row.get("ok", "")).lower() in ("true", "1") and
            bool(row.get("token")) and parsed.hostname == "hdock.phys.hust.edu.cn")


def latest_jobs(path: Path) -> dict:
    output = {}
    for row in read_log(path):
        name = row["jobname"]
        # Un intento posterior fallido no debe hacer perder un envío aceptado.
        if name not in output or not accepted(output[name]) or accepted(row):
            output[name] = row
    return output


class BatchRunner:
    def __init__(self, script: str, python: str, output: Path, callback=lambda event: None):
        self.script = Path(script).expanduser().resolve()
        self.python = python
        self.output = Path(output)
        self.callback = callback
        self.stop_event = threading.Event()
        self.process = None

    def stop(self):
        # Espera a que termine el par activo: matar Chromium puede perder un token.
        self.stop_event.set()

    def run(self, jobs: list, delay: float = 5, retry_failed: bool = False) -> None:
        if not self.script.is_file():
            raise ValueError("Selecciona el archivo hdock_batch.py instalado.")
        if delay < 0:
            raise ValueError("El intervalo no puede ser negativo.")
        self.output.mkdir(parents=True, exist_ok=True)
        marker = self.output / "submission-in-flight.json"
        if marker.exists():
            interrupted = json.loads(marker.read_text(encoding="utf-8"))
            recovered = read_log(Path(interrupted["attempt"]) / "run-log.csv")
            if recovered and accepted(recovered[-1]):
                self._append(recovered[-1])
                marker.unlink()
            else:
                raise ValueError("Envío interrumpido sin token confirmado. Revisa submission-in-flight.json y la consola del intento. "
                                 "Concilia el token en run-log.csv o archiva el marcador antes de reintentar, para evitar duplicados.")
        known = latest_jobs(self.output / "run-log.csv")
        pending = [job for job in jobs if job["jobname"] not in known or
                   (retry_failed and not accepted(known[job["jobname"]]))]
        self.callback({"kind": "message", "text": f"{len(jobs)-len(pending)} pares previos conservados; {len(pending)} por intentar."})
        for number, job in enumerate(pending, 1):
            if self.stop_event.is_set():
                break
            # Un proceso por par evita que una excepción upstream aborte el lote.
            attempt = self.output / "attempts" / job["jobname"] / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            attempt.mkdir(parents=True)
            input_csv = attempt / "job.csv"
            with input_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["receptor_pdb", "ligand_pdb", "jobname", "email"])
                writer.writeheader()
                writer.writerow({key: job.get(key, "") for key in writer.fieldnames})
            # Registro previo: un corte entre envío y bitácora requiere conciliación.
            marker = self.output / "submission-in-flight.json"
            marker.write_text(json.dumps({"jobname": job["jobname"], "attempt": str(attempt)}, indent=2), encoding="utf-8")
            command = [self.python, "-u", str(self.script), str(input_csv.resolve()), "--out", str(attempt.resolve()), "-j", "1"]
            self.callback({"kind": "message", "text": f"Enviando {job['jobname']} ({number}/{len(pending)})"})
            try:
                with (attempt / "console.log").open("w", encoding="utf-8") as console:
                    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                    local_browsers = Path(__file__).resolve().parent / ".playwright-browsers"
                    if local_browsers.is_dir():
                        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(local_browsers)
                    self.process = subprocess.Popen(command, cwd=str(self.script.parent), stdout=subprocess.PIPE,
                                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                                    env=environment,
                                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    for line in self.process.stdout:
                        console.write(line)
                        console.flush()
                        self.callback({"kind": "message", "text": line.rstrip()})
                    code = self.process.wait()
                rows = read_log(attempt / "run-log.csv")
                row = rows[-1] if rows else {"jobname": job["jobname"], "ok": False,
                    "error": f"Sin token registrado (salida {code}); revisa {attempt / 'console.log'} antes de reintentar."}
                row["jobname"] = job["jobname"]
                row["timestamp"] = datetime.now(timezone.utc).isoformat()
                self._append(row)
                self.callback({"kind": "job", "row": row})
                marker.unlink(missing_ok=True)
            finally:
                if self.process and self.process.stdout:
                    self.process.stdout.close()
                self.process = None
            if number < len(pending):
                self.stop_event.wait(delay)

    def _append(self, row):
        path = self.output / "run-log.csv"
        needs_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS, extrasaction="ignore")
            if needs_header:
                writer.writeheader()
            writer.writerow(row)
