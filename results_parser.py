"""Lee tablas HTML de HDOCK y exporta resultados sin inventar scores."""
from __future__ import annotations

import math
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from openpyxl.styles import Font, PatternFill

from data_fetcher import session
from job_runner import accepted, latest_jobs

COLUMNS = ["Ligando", "Receptor", "Categoria_Receptor", "Docking_Score", "Job_Token", "URL_Resultado", "Estado", "Error", "Jobname", "Motor", "Modelos_Descargados", "Carpeta_Modelos", "Error_Descarga", "Ultima_Consulta"]
COLUMNS += ['Fuente_Ligando','Fuente_Receptor','pLDDT_Ligando','pLDDT_Receptor']
COLUMNS += ['Metodo_Ligando','Metodo_Receptor','Origen_Ligando','Origen_Receptor','Calidad_Ligando','Calidad_Receptor']


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.rows, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.tables.append(self.rows)
            self.rows = None


def best_score(html: str):
    """Lee Docking Score en filas o columnas; ignora confianza y RMSD."""
    parser = Tables()
    parser.feed(html)
    scores = []
    for table in parser.tables:
        index = None
        for row in table:
            labels = [re.sub(r"[^a-z]", "", value.lower()) for value in row]
            if "dockingscore" in labels:
                position = labels.index("dockingscore")
                # HDOCK presenta una fila por métrica y una columna por modelo.
                values = row[position + 1:]
                row_scores = []
                for value in values:
                    try:
                        number = float(value.replace("−", "-"))
                        if math.isfinite(number):
                            row_scores.append(number)
                    except ValueError:
                        pass
                if row_scores:
                    scores.extend(row_scores)
                    index = None
                else:
                    index = position
                continue
            if index is not None and len(row) > index:
                try:
                    number = float(row[index].replace("−", "-"))
                    if math.isfinite(number):
                        scores.append(number)
                except ValueError:
                    pass
    return min(scores) if scores else None


def fetch_score(url: str, client=None):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname != "hdock.phys.hust.edu.cn" or parsed.username:
        raise ValueError("La URL no pertenece al servidor HDOCK esperado.")
    # Las redirecciones se notifican para revisar cambios de servidor.
    response = (client or session()).get(url, timeout=(10, 45), allow_redirects=False)
    response.raise_for_status()
    if 300 <= response.status_code < 400:
        raise ValueError("HDOCK redirigió la URL; revisa el enlace manualmente.")
    return best_score(response.text), response.text


def summary(jobs: list, log_path: Path, results: dict, local=False) -> pd.DataFrame:
    logs = latest_jobs(log_path)
    rows = []
    for job in jobs:
        log = logs.get(job["jobname"], {})
        result = results.get(job["jobname"], {})
        # Nunca reutilizar el resultado de otro token.
        if not local and result.get("token") != log.get("token"):
            result = {}
        state = "preparado" if not log else "error_envio"
        if accepted(log):
            state = result.get("state", "enviado")
        if local:
            log = {}
            state = result.get('state', 'preparado')
        rows.append(dict(zip(COLUMNS, [job.get("Ligando", job.get("RBP", "")), job["Receptor"], job["Categoria_Receptor"],
            result.get("score"), log.get("token", ""), log.get("result_url", ""), state,
            result.get("error", log.get("error", "")), job["jobname"], 'HDOCKlite local' if local else 'HDOCK servidor',
            len(result.get('models', [])), result.get('model_directory', ''), result.get('download_error', ''), result.get('checked_at', ''),
            job.get('Fuente_Ligando','Desconocida'),job.get('Fuente_Receptor','Desconocida'),job.get('pLDDT_Ligando'),job.get('pLDDT_Receptor'),
            job.get('Metodo_Ligando',''),job.get('Metodo_Receptor',''),job.get('Origen_Ligando',''),job.get('Origen_Receptor',''),
            job.get('Calidad_Ligando',''),job.get('Calidad_Receptor','')])))
    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["Docking_Score"] = pd.to_numeric(frame["Docking_Score"], errors="coerce")
    return frame.sort_values("Docking_Score", ascending=True, na_position="last", kind="stable")


def safe_cell(value):
    # Una etiqueta externa no debe convertirse en fórmula al abrir CSV/Excel.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export(frame: pd.DataFrame, base: Path) -> tuple:
    base = Path(base)
    base.parent.mkdir(parents=True, exist_ok=True)
    safe = frame.apply(lambda column: column.map(safe_cell))
    csv_path, xlsx_path = base.with_suffix(".csv"), base.with_suffix(".xlsx")
    safe.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        safe.to_excel(writer, sheet_name="Resultados", index=False)
        sheet = writer.sheets["Resultados"]
        sheet.freeze_panes = "D2"
        sheet.auto_filter.ref = sheet.dimensions
        widths = [24, 28, 22, 20, 28, 62, 24, 60, 34]
        for index, cell in enumerate(sheet[1]):
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="173B4F")
            sheet.column_dimensions[cell.column_letter].width = widths[index] if index < len(widths) else 28
        for row in sheet.iter_rows(min_row=2):
            row[3].number_format = "0.000"
            if row[2].value == "control":
                for cell in row:
                    cell.fill = PatternFill("solid", fgColor="FFF0CB")
    return csv_path, xlsx_path
