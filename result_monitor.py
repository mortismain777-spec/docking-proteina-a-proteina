"""Vigilancia de trabajos enviados: independiente de la ventana Tkinter."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from desktop_notify import notify
from job_runner import accepted, latest_jobs
from pipeline import Pipeline, now, write_json
from results_parser import export


class MonitorLock:
    def __init__(self, directory):
        self.path = Path(directory) / '.monitor.lock'
        self.handle = None

    def acquire(self):
        self.handle = self.path.open('a+b')
        self.handle.seek(0, 2)
        if self.handle.tell() == 0:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.handle.close()
            self.handle = None
            return False

    def close(self):
        if self.handle:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None


def running(directory):
    lock = MonitorLock(directory)
    if lock.acquire():
        lock.close()
        return False
    return True


def start_monitor(directory: Path, interval=300, count=5, notifications=True):
    directory = Path(directory).resolve()
    if running(directory):
        (directory / 'monitor_refresh.request').touch()
        return None
    (directory / 'monitor_stop.request').unlink(missing_ok=True)
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.with_name('pythonw.exe').exists():
        executable = executable.with_name('pythonw.exe')
    command = [str(executable), str(Path(__file__).resolve()), '--batch', str(directory), '--interval', str(interval), '--models', str(count)]
    if not notifications:
        command.append('--no-notify')
    with (directory / 'monitor.log').open('a', encoding='utf-8') as console:
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=console, stderr=subprocess.STDOUT,
                                creationflags=(getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)))


def cycle(directory: Path, previous: dict, count: int, notifications: bool) -> dict:
    pipeline = Pipeline.load(directory)
    pipeline.collect(download_count=count, persist=False)
    logs = latest_jobs(directory / 'run-log.csv')
    submitted = {job['jobname']: logs[job['jobname']] for job in pipeline.config['jobs'] if accepted(logs.get(job['jobname'], {}))}
    results = pipeline.config['results']
    notified = set(previous.get('notified', []))
    ready, all_complete = [], bool(submitted)
    for name, row in submitted.items():
        result = results.get(name, {})
        complete = result.get('token') == row['token'] and result.get('state') == 'completado'
        key = name + ':' + row['token']
        if complete and key not in notified:
            ready.append(key)
        models_ready = len(result.get('models', [])) >= count
        all_complete = all_complete and complete and models_ready
    state = {'pid': os.getpid(), 'updated_at': now(), 'results': results,
             'status': 'completado' if all_complete else ('consultando' if submitted else 'sin_envios'),
             'submitted': len(submitted), 'notified': sorted(notified), 'notification_error': ''}
    if ready:
        if notifications:
            ok, error = notify('Resultados de HDOCK disponibles', f'{len(ready)} par(es) tienen score. Abre Docking Matrix para consultar y ver los modelos.')
            state['notification_error'] = error
            state['notification_requested'] = ok
        notified.update(ready)
        state['notified'] = sorted(notified)
    write_json(directory / 'monitor_state.json', state)
    # Un Excel abierto no debe perder resultados ni repetir notificaciones.
    try:
        export(pipeline.table(), directory / 'resumen_hdock_auto')
    except Exception as exc:
        state['export_error'] = str(exc)
        write_json(directory / 'monitor_state.json', state)
    return state


def monitor(directory: Path, interval=300, count=5, notifications=True, max_hours=48):
    if not 60 <= interval <= 3600 or not 1 <= count <= 20:
        raise ValueError('Intervalo entre 60 y 3600 segundos; modelos entre 1 y 20.')
    lock = MonitorLock(directory)
    if not lock.acquire():
        return
    state_path = directory / 'monitor_state.json'
    try:
        previous = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
        started = time.monotonic()
        failures = 0
        while time.monotonic() - started < max_hours * 3600:
            if (directory / 'monitor_stop.request').exists():
                previous.update(status='detenido', updated_at=now())
                write_json(state_path, previous)
                return
            try:
                previous = cycle(directory, previous, count, notifications)
                failures = 0
            except Exception as exc:
                failures += 1
                previous.update(status='error_consulta', error=str(exc), updated_at=now())
                write_json(state_path, previous)
            if previous.get('status') in ('completado', 'sin_envios'):
                return
            wait_until = time.monotonic() + min(interval * (2 ** min(failures, 3)), 3600)
            while time.monotonic() < wait_until:
                refresh = directory / 'monitor_refresh.request'
                if refresh.exists():
                    refresh.unlink(missing_ok=True)
                    break
                if (directory / 'monitor_stop.request').exists():
                    break
                time.sleep(1)
        previous.update(status='plazo_agotado', updated_at=now())
        write_json(state_path, previous)
        if notifications:
            notify('Seguimiento de HDOCK detenido', 'Se alcanzaron 48 horas. Abre la app para revisar y reactivar la consulta si hace falta.')
    finally:
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True)
    parser.add_argument('--interval', type=int, default=300)
    parser.add_argument('--models', type=int, default=5)
    parser.add_argument('--no-notify', action='store_true')
    args = parser.parse_args()
    monitor(Path(args.batch), args.interval, args.models, not args.no_notify)
