"""Aplicación de escritorio: los hilos de trabajo nunca modifican widgets."""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from job_runner import BatchRunner, accepted, latest_jobs
from pipeline import Pipeline, protein_key, protein_label, read_inputs
from results_parser import COLUMNS, export

ROOT = Path(__file__).resolve().parent


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Docking Matrix · Proteína–proteína")
        self.geometry("1180x800")
        self.minsize(980, 680)
        self.configure(background="#eef3f7")
        self.pipeline = None
        self.local = {}
        self.events = queue.Queue()
        self.busy = False
        self.stop_event = threading.Event()
        self.runner = None
        self.actions = []
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self._build()
        self.after(150, self.poll)

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#eef3f7")
        style.configure("TLabel", background="#eef3f7", foreground="#173b4f")
        style.configure("TButton", padding=(12, 7))
        style.configure("TNotebook.Tab", padding=(18, 9))
        style.configure("Treeview", rowheight=28)
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
        header = ttk.Frame(self, padding=(24, 16))
        header.pack(fill="x")
        ttk.Label(header, text="Docking Matrix", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Proteína–proteína  /  Preparar → Enviar → Consultar → Exportar").pack(anchor="w", pady=(3, 0))
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=20)
        inputs, execution, results = [ttk.Frame(self.notebook, padding=16) for _ in range(3)]
        for panel, label in zip([inputs, execution, results], ["1 · Proteínas", "2 · Lote y seguimiento", "3 · Resultados"]):
            self.notebook.add(panel, text=label)

        toolbar = ttk.Frame(inputs)
        toolbar.pack(fill="x")
        self.button(toolbar, "Cargar CSV", self.load_csv)
        self.button(toolbar, "Cargar ejemplo", self.example)
        self.button(toolbar, "Añadir listas pegadas", self.paste_dialog)
        self.button(toolbar, "Asignar PDB local", self.local_dialog)
        ttk.Label(inputs, text="Edita o pega el CSV: tipo,identificador,nombre_comun,categoria").pack(anchor="w", pady=(14, 5))
        self.editor = tk.Text(inputs, height=12, font=("Consolas", 11), wrap="none", undo=True)
        self.editor.pack(fill="both", expand=True)
        self.editor.insert("1.0", "tipo,identificador,nombre_comun,categoria\n")
        options = ttk.Frame(inputs)
        options.pack(fill="x", pady=12)
        self.taxon, self.email = tk.StringVar(value="9606"), tk.StringVar()
        self.dummy = tk.BooleanVar()
        ttk.Label(options, text="Organismo (TaxID; 9606 = humano):").pack(side="left")
        ttk.Entry(options, textvariable=self.taxon, width=10).pack(side="left", padx=(6, 18))
        ttk.Label(options, text="Email HDOCK (opcional):").pack(side="left")
        ttk.Entry(options, textvariable=self.email, width=28).pack(side="left", padx=6)
        ttk.Checkbutton(inputs, text="Añadir ubiquitina 1UBQ como segundo control de referencia", variable=self.dummy).pack(anchor="w")
        ttk.Label(inputs, text="Se añade albúmina bovina P02769 como control provisional. Puedes añadir receptores de categoría control.\nValida los controles y prepara cadenas/dominios antes de interpretar diferencias de score.", wraplength=1000).pack(anchor="w", pady=8)
        self.local_label = ttk.Label(inputs, text="PDB locales asignados: 0")
        self.local_label.pack(anchor="w")
        self.button(inputs, "Crear lote y preparar estructuras", self.prepare, side="top")

        settings = ttk.LabelFrame(execution, text="Motor de envío", padding=12)
        settings.pack(fill="x")
        self.script = tk.StringVar()
        self.python = tk.StringVar(value=sys.executable)
        self.delay = tk.StringVar(value="5")
        for row, (label, variable, command) in enumerate([
            ("hdock_batch.py", self.script, self.pick_script), ("Python del motor", self.python, self.pick_python),
        ]):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=4)
            ttk.Entry(settings, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8)
            ttk.Button(settings, text="Buscar…", command=command).grid(row=row, column=2)
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text="Segundos entre pares:").grid(row=2, column=0, sticky="w", pady=8)
        ttk.Entry(settings, textvariable=self.delay, width=10).grid(row=2, column=1, sticky="w", padx=8)
        self.retry = tk.BooleanVar()
        ttk.Checkbutton(settings, text="Reintentar envíos fallidos ya revisados", variable=self.retry).grid(row=3, column=0, columnspan=3, sticky="w")
        bar = ttk.Frame(execution)
        bar.pack(fill="x", pady=12)
        self.button(bar, "Abrir lote / reanudar", self.open_batch)
        self.button(bar, "Revisar estructuras pendientes", self.retry_structures)
        self.button(bar, "Enviar pendientes", self.send)
        self.button(bar, "Actualizar resultados", self.collect)
        ttk.Button(bar, text="Detener al acabar el par", command=self.stop).pack(side="left", padx=4)
        self.batch_label = ttk.Label(execution, text="Ningún lote seleccionado", wraplength=1050)
        self.batch_label.pack(anchor="w", pady=6)
        self.counts = tk.StringVar(value="Preparados: 0  |  Enviados: 0  |  Con score: 0  |  Errores: 0")
        ttk.Label(execution, textvariable=self.counts, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=8)
        self.progress = ttk.Progressbar(execution, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 10))
        self.console = tk.Text(execution, height=14, background="#142c3b", foreground="#dcebf4", font=("Consolas", 10), wrap="word", state="disabled")
        self.console.pack(fill="both", expand=True)

        filters = ttk.Frame(results)
        filters.pack(fill="x", pady=(0, 12))
        ttk.Label(filters, text="Categoría:").pack(side="left")
        self.category = tk.StringVar(value="Todas")
        combo = ttk.Combobox(filters, textvariable=self.category, values=["Todas", "A", "B", "C", "control"], width=14, state="readonly")
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda event: self.refresh())
        self.button(filters, "Exportar vista CSV + Excel", self.export_view)
        self.button(filters, "Abrir URL seleccionada", self.open_result)
        table_area = ttk.Frame(results)
        table_area.pack(fill="both", expand=True)
        table_area.rowconfigure(0, weight=1)
        table_area.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_area, columns=COLUMNS, show="headings")
        for col in COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=160 if col != "URL_Resultado" else 340, minwidth=100)
        self.tree.tag_configure("control", background="#fff0cb")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table_area, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table_area, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        ttk.Label(results, text="Orden: score de menor a mayor; pendientes al final. Controles resaltados en amarillo.\nEl score no equivale a afinidad experimental. Enviado indica recepción, no cálculo terminado.").pack(anchor="w", pady=10)
        self.status = tk.StringVar(value="Listo · Carga un CSV o pega tus proteínas para comenzar.")
        ttk.Label(self, textvariable=self.status, padding=(24, 12)).pack(fill="x")

    def button(self, parent, label, command, side="left"):
        button = ttk.Button(parent, text=label, command=command)
        button.pack(side=side, padx=3, pady=3)
        self.actions.append(button)
        return button

    def guarded(self, operation):
        try:
            operation()
        except Exception as exc:
            messagebox.showerror("No se pudo continuar", str(exc))

    def load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if path:
            self.guarded(lambda: self.set_text(Path(path).read_text(encoding="utf-8-sig")))

    def set_text(self, text):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)

    def example(self):
        self.set_text((ROOT / "ejemplo_entrada.csv").read_text(encoding="utf-8-sig"))

    def paste_dialog(self):
        window = tk.Toplevel(self)
        window.title("Pegar listas · un identificador por línea")
        panels = ttk.Frame(window, padding=14)
        panels.pack()
        ttk.Label(panels, text="Ligandos (proteínas)").grid(row=0, column=0)
        ttk.Label(panels, text="Receptores (se añaden con categoría A)").grid(row=0, column=1)
        ligands, recs = tk.Text(panels, width=35, height=14), tk.Text(panels, width=35, height=14)
        ligands.grid(row=1, column=0, padx=5)
        recs.grid(row=1, column=1, padx=5)
        def add():
            import csv, io
            output = io.StringIO()
            writer = csv.writer(output)
            for kind, widget in [("ligando", ligands), ("receptor", recs)]:
                for identifier in widget.get("1.0", "end").splitlines():
                    if identifier.strip():
                        writer.writerow([kind, identifier.strip(), identifier.strip(), "A" if kind == "receptor" else ""])
            self.editor.insert("end", "\n" + output.getvalue())
            window.destroy()
        ttk.Button(panels, text="Añadir al CSV editable", command=add).grid(row=2, column=0, columnspan=2, pady=10)

    def local_dialog(self):
        def operation():
            items = self.pipeline.config["proteins"] if self.pipeline else read_inputs(self.editor.get("1.0", "end"))
            window = tk.Toplevel(self)
            window.title("Asignar estructura local")
            keys_by_label = {protein_label(item): protein_key(item) for item in items}
            variable = tk.StringVar(value=protein_label(items[0]))
            ttk.Label(window, text="Selecciona la proteína y luego un archivo PDB:", padding=10).pack()
            ttk.Combobox(window, textvariable=variable, values=list(keys_by_label), state="readonly", width=50).pack(padx=12)
            def assign():
                path = filedialog.askopenfilename(filetypes=[("PDB", "*.pdb")], parent=window)
                if path:
                    key = keys_by_label[variable.get()]
                    if self.pipeline and key in self.pipeline.config["structures"]:
                        messagebox.showinfo("Estructura fijada", "Esta estructura ya está preparada. Crea otro lote para cambiarla.")
                        return
                    self.local[key] = str(Path(path).resolve())
                    if self.pipeline:
                        self.pipeline.config["local_pdb"][key] = self.local[key]
                        self.pipeline.save()
                    self.local_label.config(text=f"PDB locales asignados: {len(self.local)}")
                    window.destroy()
            ttk.Button(window, text="Elegir PDB…", command=assign).pack(pady=12)
        self.guarded(operation)

    def pick_script(self):
        path = filedialog.askopenfilename(filetypes=[("Script Python", "*.py")])
        if path:
            self.script.set(path)

    def pick_python(self):
        path = filedialog.askopenfilename(title="Python con pandas y Playwright instalados")
        if path:
            self.python.set(path)

    def prepare(self):
        def operation():
            items = read_inputs(self.editor.get("1.0", "end"))
            taxon = int(self.taxon.get())
            if taxon <= 0:
                raise ValueError("El TaxID debe ser un entero positivo.")
            parent = filedialog.askdirectory(title="Carpeta donde crear un lote nuevo")
            if not parent:
                return
            folder = Path(parent) / datetime.now().strftime("lote_%Y%m%d_%H%M%S")
            self.pipeline = Pipeline.create(folder, items, taxon, dict(self.local), self.dummy.get(), self.email.get().strip())
            self.run_task(lambda: self.pipeline.prepare(self.events.put, self.stop_event), "Preparando estructuras…")
        self.guarded(operation)

    def retry_structures(self):
        if self.require_batch():
            self.run_task(lambda: self.pipeline.prepare(self.events.put, self.stop_event), "Revisando estructuras…")

    def open_batch(self):
        path = filedialog.askdirectory(title="Carpeta con pipeline_config.json y run-log.csv")
        if path:
            def operation():
                self.pipeline = Pipeline.load(Path(path))
                self.local = dict(self.pipeline.config["local_pdb"])
                self.local_label.config(text=f"PDB locales asignados: {len(self.local)}")
                engine = self.pipeline.config.get("engine", {})
                self.script.set(engine.get("script", self.script.get()))
                self.python.set(engine.get("python", self.python.get()))
                self.refresh()
                self.notebook.select(1)
            self.guarded(operation)

    def require_batch(self):
        if self.pipeline is None:
            messagebox.showinfo("Selecciona un lote", "Prepara las estructuras o abre un lote existente.")
            return False
        return True

    def send(self):
        def operation():
            if not self.require_batch():
                return
            self.pipeline.verify_structures()
            if not self.pipeline.config["jobs"]:
                raise ValueError("No hay pares preparados; revisa los errores de estructuras.")
            script = self.script.get().strip()
            if not Path(script).is_file():
                raise ValueError("Selecciona hdock_batch.py antes de enviar.")
            delay = float(self.delay.get())
            if delay < 0 or not __import__('math').isfinite(delay):
                raise ValueError("Intervalo inválido.")
            if not messagebox.askyesno("Enviar a HDOCK", f"Se enviarán los PDB de los pares pendientes del lote a HDOCK.\nMatriz preparada: {len(self.pipeline.config['jobs'])} pares.\n¿Iniciar el envío?"):
                return
            self.pipeline.config["engine"] = {"script": str(Path(script).resolve()), "python": self.python.get(), "delay": delay}
            from data_fetcher import sha256
            self.pipeline.config["engine"]["script_sha256"] = sha256(Path(script))
            self.pipeline.save()
            self.runner = BatchRunner(script, self.python.get(), self.pipeline.directory, self.events.put)
            retry = self.retry.get()
            def work():
                self.runner.run(self.pipeline.config["jobs"], delay, retry)
                if not self.stop_event.is_set():
                    self.pipeline.collect(self.events.put, self.stop_event)
            self.run_task(work, "Enviando pares…")
        self.guarded(operation)

    def collect(self):
        if self.require_batch():
            self.run_task(lambda: self.pipeline.collect(self.events.put, self.stop_event), "Consultando HDOCK…")

    def run_task(self, operation, status):
        if self.busy:
            return
        self.busy = True
        self.stop_event.clear()
        for button in self.actions:
            button.config(state="disabled")
        self.status.set(status)
        self.notebook.select(1)
        def worker():
            try:
                operation()
                # Cada fase deja una tabla completa persistente, incluidos pendientes.
                export(self.pipeline.table(), self.pipeline.directory / "resumen")
            except Exception as exc:
                self.events.put({"kind": "error", "text": str(exc)})
            finally:
                self.events.put({"kind": "done"})
        threading.Thread(target=worker, daemon=True).start()

    def stop(self):
        self.stop_event.set()
        if self.runner:
            self.runner.stop()
        self.status.set("Detención solicitada; esperando el par o la consulta activa.")

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event["kind"]
                if kind in ("message", "error"):
                    self.console.config(state="normal")
                    self.console.insert("end", event["text"] + "\n")
                    self.console.see("end")
                    self.console.config(state="disabled")
                    if kind == "error":
                        messagebox.showerror("Error del pipeline", event["text"])
                elif kind == "job":
                    row = event["row"]
                    self.console.config(state="normal")
                    self.console.insert("end", f"{row['jobname']} | token={row.get('token', '')} | {row.get('error', '')}\n")
                    self.console.config(state="disabled")
                    self.refresh()
                elif kind == "done":
                    self.busy = False
                    for button in self.actions:
                        button.config(state="normal")
                    self.status.set("Fase terminada. Revisa el registro y actualiza los resultados si siguen pendientes.")
                    self.refresh()
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def filtered(self):
        frame = self.pipeline.table()
        if self.category.get() != "Todas":
            frame = frame[frame["Categoria_Receptor"] == self.category.get()]
        return frame

    def refresh(self):
        if not self.pipeline:
            return
        import pandas as pd
        frame = self.pipeline.table()
        logs = latest_jobs(self.pipeline.directory / "run-log.csv")
        sent = sum(accepted(logs.get(job["jobname"], {})) for job in self.pipeline.config["jobs"])
        errors = len(self.pipeline.config["errors"]) + int(frame["Estado"].str.startswith("error").sum())
        self.counts.set(f"Preparados: {len(frame)}  |  Enviados: {sent}  |  Con score: {frame['Docking_Score'].notna().sum()}  |  Errores: {errors}  |  Pares omitidos: {len(self.pipeline.config.get('skipped_pairs', []))}")
        self.progress.config(maximum=max(1, len(frame)), value=int(frame["Docking_Score"].notna().sum()))
        self.batch_label.config(text=f"Lote: {self.pipeline.directory}")
        self.tree.delete(*self.tree.get_children())
        for _, row in self.filtered().iterrows():
            values = ["" if pd.isna(row[col]) else row[col] for col in COLUMNS]
            self.tree.insert("", "end", values=values, tags=("control",) if row["Categoria_Receptor"] == "control" else ())

    def export_view(self):
        if not self.require_batch():
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="resultados_filtrados.csv", filetypes=[("CSV y Excel", "*.csv")])
        if path:
            self.guarded(lambda: export(self.filtered(), Path(path)))

    def open_result(self):
        selection = self.tree.selection()
        if selection:
            url = self.tree.item(selection[0], "values")[5]
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.hostname == "hdock.phys.hust.edu.cn" and parsed.scheme in ("http", "https"):
                webbrowser.open(url)

    def close_app(self):
        if self.busy:
            messagebox.showinfo("Operación activa", "Pulsa Detener y espera al par activo antes de cerrar para conservar su token.")
        else:
            self.destroy()


if __name__ == "__main__":
    App().mainloop()
