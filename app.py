"""Preparación, cálculo local/servidor, modelos y avisos de escritorio."""
from __future__ import annotations
import csv
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from desktop_notify import notify
from job_runner import BatchRunner, accepted, latest_jobs
from local_engine import LocalEngine
from pipeline import Pipeline, protein_key, protein_label, read_inputs, write_json
from result_monitor import running, start_monitor
from results_parser import COLUMNS, export

ROOT = Path(__file__).resolve().parent
STATE_LABELS = {'preparado':'Listo para ejecutar', 'enviado':'Aceptado por HDOCK', 'completado':'Score disponible',
                'pendiente_o_formato_desconocido':'Sin tabla de score todavía', 'error_envio':'Falló el envío',
                'error_consulta':'Falló la consulta', 'error_local':'Falló el cálculo local'}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Docking Matrix · Proteína–proteína')
        self.geometry(f'{min(1240,self.winfo_screenwidth()-80)}x{min(800,self.winfo_screenheight()-100)}')
        self.minsize(980,min(680,self.winfo_screenheight()-100))
        self.pipeline, self.local, self.runner = None, {}, None
        self.events, self.stop_event = queue.Queue(), threading.Event()
        self.busy, self.actions, self.last_refresh = False, [], 0
        self.preferences = {}
        try:
            self.preferences = json.loads((ROOT/'user_settings.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):
            pass
        self.protocol('WM_DELETE_WINDOW',self.close_app)
        self._build()
        self.after(200,self.poll)

    def button(self,parent,text,command,grid=None):
        button = ttk.Button(parent,text=text,command=command)
        if grid:
            button.grid(row=grid[0],column=grid[1],padx=3,pady=3,sticky='w')
        else:
            button.pack(side='left',padx=3,pady=3)
        self.actions.append(button)
        return button

    def _build(self):
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('TFrame',background='#edf3f7'); style.configure('TLabel',background='#edf3f7',foreground='#183b50')
        style.configure('TButton',padding=(9,6)); style.configure('TNotebook.Tab',padding=(16,8)); style.configure('Treeview',rowheight=28)
        self.configure(background='#edf3f7')
        header=ttk.Frame(self,padding=(20,12)); header.pack(fill='x')
        ttk.Label(header,text='Docking Matrix',font=('Segoe UI',23,'bold')).pack(anchor='w')
        ttk.Label(header,text='Preparar proteínas → Calcular en el equipo o enviar a HDOCK → Ver modelos y exportar').pack(anchor='w')
        self.notebook=ttk.Notebook(self); self.notebook.pack(fill='both',expand=True,padx=18)
        inputs,execution,results=[ttk.Frame(self.notebook,padding=12) for _ in range(3)]
        for panel,label in zip((inputs,execution,results),('1 · Proteínas','2 · Ejecución y seguimiento','3 · Resultados y modelos')):
            self.notebook.add(panel,text=label)
        toolbar=ttk.Frame(inputs); toolbar.pack(fill='x')
        for label,command in [('Cargar CSV',self.load_csv),('Pegar listas de proteínas',self.paste_dialog),('Cargar ejemplo',self.example),('Asignar PDB propio',self.local_dialog)]:
            self.button(toolbar,label,command)
        ttk.Label(inputs,text='CSV: tipo, identificador, nombre_comun, categoria. Tipo: ligando/receptor. Categoría: A/B/C/control.').pack(anchor='w',pady=(10,4))
        self.editor=tk.Text(inputs,height=9,font=('Consolas',11),wrap='none',undo=True); self.editor.pack(fill='both',expand=True)
        self.editor.insert('1.0','tipo,identificador,nombre_comun,categoria\n')
        options=ttk.Frame(inputs); options.pack(fill='x',pady=8)
        self.taxon,self.email=tk.StringVar(value='9606'),tk.StringVar()
        ttk.Label(options,text='Organismo (TaxID):').pack(side='left'); ttk.Entry(options,textvariable=self.taxon,width=9).pack(side='left',padx=6)
        ttk.Label(options,text='9606 = humano; se usa al buscar por nombre o gen.').pack(side='left')
        self.albumin,self.dummy=tk.BooleanVar(value=False),tk.BooleanVar(value=False)
        refs=ttk.Frame(inputs); refs.pack(fill='x')
        ttk.Checkbutton(refs,text='Añadir albúmina como referencia provisional',variable=self.albumin).pack(side='left')
        ttk.Checkbutton(refs,text='Añadir ubiquitina 1UBQ como referencia provisional',variable=self.dummy).pack(side='left',padx=12)
        selection=ttk.Frame(inputs); selection.pack(fill='x',pady=6)
        self.region=tk.StringVar(value='Estructura completa')
        ttk.Label(selection,text='Región a preparar:').pack(side='left')
        ttk.Combobox(selection,textvariable=self.region,values=['Estructura completa','Región extracelular anotada en UniProt'],state='readonly',width=44).pack(side='left',padx=6)
        ttk.Label(inputs,text='Descarga y preparación de átomos pesados. Columnas opcionales: residuo_inicio,residuo_fin,cadenas.\nUn nombre ambiguo requiere UniProt ID. No se reconstruyen residuos ni se inventan controles negativos.',wraplength=1120).pack(anchor='w',pady=5)
        self.local_label=ttk.Label(inputs,text='PDB propios asignados: 0'); self.local_label.pack(anchor='w')
        prepbar=ttk.Frame(inputs); prepbar.pack(fill='x',pady=6)
        for label,command in [('Preparar proteínas y crear pares',self.prepare),('Reintentar preparación que falló',self.retry_structures),('Ver informe de preparación',self.open_preparation)]:
            self.button(prepbar,label,command)

        self.modebar=ttk.Frame(execution); self.modebar.pack(fill='x')
        self.mode=tk.StringVar(value='Servidor HDOCK')
        ttk.Label(self.modebar,text='Dónde realizar el cálculo:').pack(side='left')
        self.mode_combo=ttk.Combobox(self.modebar,textvariable=self.mode,values=['Servidor HDOCK','Este equipo · HDOCKlite'],state='readonly',width=30)
        self.mode_combo.pack(side='left',padx=8); self.mode_combo.bind('<<ComboboxSelected>>',lambda event:self.mode_changed())
        self.button(self.modebar,'Abrir lote guardado',self.open_batch)
        self.cloud_frame=ttk.LabelFrame(execution,text='Servidor: los PDB se envían a HDOCK',padding=8); self.cloud_frame.pack(fill='x',pady=8)
        script=ROOT/'hdock_batch/hdock_batch.py'
        self.script=tk.StringVar(value=str(script) if script.exists() else '')
        self.python,self.delay=tk.StringVar(value=sys.executable),tk.StringVar(value='5')
        for row,(label,variable,command) in enumerate([('Script hdock_batch.py:',self.script,self.pick_script),('Python del motor:',self.python,self.pick_python)]):
            ttk.Label(self.cloud_frame,text=label).grid(row=row,column=0,sticky='w',pady=3)
            ttk.Entry(self.cloud_frame,textvariable=variable).grid(row=row,column=1,sticky='ew',padx=8)
            self.button(self.cloud_frame,'Buscar…',command,grid=(row,2))
        self.cloud_frame.columnconfigure(1,weight=1)
        ttk.Label(self.cloud_frame,text='Pausa entre envíos (s):').grid(row=2,column=0,sticky='w')
        ttk.Entry(self.cloud_frame,textvariable=self.delay,width=8).grid(row=2,column=1,sticky='w',padx=8)
        ttk.Label(self.cloud_frame,text='Email opcional para HDOCK:').grid(row=3,column=0,sticky='w')
        ttk.Entry(self.cloud_frame,textvariable=self.email,width=28).grid(row=3,column=1,sticky='w',padx=8)
        self.retry=tk.BooleanVar(value=False)
        ttk.Checkbutton(self.cloud_frame,text='Reintentar sólo envíos con error, después de revisar sus registros',variable=self.retry).grid(row=4,column=0,columnspan=3,sticky='w',pady=4)
        self.local_frame=ttk.LabelFrame(execution,text='Local: HDOCKlite global ab initio (Linux o WSL)',padding=8)
        self.tool_directory=tk.StringVar(value=self.preferences.get('tools',str(ROOT/'tools/hdocklite')))
        self.distribution=tk.StringVar(value=self.preferences.get('distribution','')); self.academic_license=tk.BooleanVar(value=False)
        ttk.Label(self.local_frame,text='Carpeta con hdock y createpl:').grid(row=0,column=0,sticky='w')
        ttk.Entry(self.local_frame,textvariable=self.tool_directory).grid(row=0,column=1,sticky='ew',padx=8)
        self.button(self.local_frame,'Buscar…',self.pick_tools,grid=(0,2))
        ttk.Label(self.local_frame,text='WSL: distribución (vacío = predeterminada):').grid(row=1,column=0,sticky='w',pady=4)
        ttk.Entry(self.local_frame,textvariable=self.distribution).grid(row=1,column=1,sticky='ew',padx=8)
        self.button(self.local_frame,'Comprobar motor local',self.check_local,grid=(2,0))
        self.button(self.local_frame,'Instalación y licencia',self.local_guide,grid=(2,1))
        ttk.Checkbutton(self.local_frame,text='He revisado la licencia de HDOCKlite y mi uso está autorizado por ella',variable=self.academic_license).grid(row=3,column=0,columnspan=3,sticky='w',pady=5)
        ttk.Label(self.local_frame,text='Búsqueda global: no requiere grid box manual. No incluye la búsqueda de plantillas del servidor.\nSe calcula un par a la vez usando CPU/RAM del equipo; revisa dominios y calidad.',wraplength=1050).grid(row=4,column=0,columnspan=3,sticky='w')
        self.local_frame.columnconfigure(1,weight=1)
        follow=ttk.Frame(execution); follow.pack(fill='x',pady=4)
        self.auto_monitor,self.notifications=tk.BooleanVar(value=True),tk.BooleanVar(value=True)
        self.minutes,self.model_count=tk.StringVar(value='5'),tk.StringVar(value='5')
        ttk.Checkbutton(follow,text='Consultar HDOCK automáticamente cada',variable=self.auto_monitor).pack(side='left')
        ttk.Spinbox(follow,from_=1,to=60,textvariable=self.minutes,width=4).pack(side='left',padx=3)
        ttk.Label(follow,text='min. Modelos por par:').pack(side='left')
        ttk.Spinbox(follow,from_=1,to=20,textvariable=self.model_count,width=4).pack(side='left',padx=3)
        ttk.Checkbutton(follow,text='Avisar en el escritorio al estar listos',variable=self.notifications).pack(side='left',padx=10)
        commands=ttk.Frame(execution); commands.pack(fill='x',pady=5)
        self.run_button=self.button(commands,'Enviar pares a HDOCK',self.send)
        consult_button=self.button(commands,'Consultar HDOCK y descargar modelos',self.collect)
        ttk.Button(commands,text='Pausar tras el par activo',command=self.stop).pack(side='left',padx=3)
        monitoring=ttk.Frame(execution); monitoring.pack(fill='x')
        self.cloud_actions=[consult_button]
        for label,command in [('Activar seguimiento en segundo plano',self.activate_monitor),('Pausar seguimiento',self.pause_monitor),('Probar notificación',self.test_notification)]:
            button=self.button(monitoring,label,command)
            if command != self.test_notification: self.cloud_actions.append(button)
        self.batch_label=ttk.Label(execution,text='Ningún lote seleccionado',wraplength=1120); self.batch_label.pack(anchor='w',pady=(8,3))
        self.counts=tk.StringVar(value='Proteínas listas: 0 | Pares preparados: 0 | Pares enviados a HDOCK: 0 | Resultados listos: 0')
        ttk.Label(execution,textvariable=self.counts,font=('Segoe UI',10,'bold'),wraplength=1120).pack(anchor='w',pady=4)
        self.monitor_status=tk.StringVar(value='El seguimiento consulta y descarga; no vuelve a enviar trabajos.')
        ttk.Label(execution,textvariable=self.monitor_status,wraplength=1120).pack(anchor='w')
        self.progress=ttk.Progressbar(execution,mode='determinate'); self.progress.pack(fill='x',pady=6)
        self.console=tk.Text(execution,height=7,background='#132d3d',foreground='#dcebf4',font=('Consolas',10),state='disabled',wrap='word'); self.console.pack(fill='both',expand=True)

        filters=ttk.Frame(results); filters.pack(fill='x',pady=(0,8))
        self.category=tk.StringVar(value='Todas'); ttk.Label(filters,text='Categoría:').pack(side='left')
        combo=ttk.Combobox(filters,textvariable=self.category,values=['Todas','A','B','C','control'],state='readonly',width=10); combo.pack(side='left',padx=6)
        combo.bind('<<ComboboxSelected>>',lambda event:self.refresh())
        self.button(filters,'Exportar tabla CSV + Excel',self.export_view); self.button(filters,'Ver página en HDOCK',self.open_result)
        tools=ttk.Frame(results); tools.pack(fill='x',pady=(0,8))
        self.button(tools,'Abrir carpeta de modelos',self.open_models); self.button(tools,'Abrir mejor modelo en visor',self.open_viewer)
        ttk.Label(results,text='Las filas aparecen al preparar pares. «Score disponible» indica un cálculo con resultado.\n«Detalle de error» explica un fallo; «Última consulta» es una fecha. El score no es afinidad experimental.',wraplength=1120).pack(anchor='w',pady=(0,8))
        area=ttk.Frame(results); area.pack(fill='both',expand=True); area.rowconfigure(0,weight=1); area.columnconfigure(0,weight=1)
        self.tree=ttk.Treeview(area,columns=COLUMNS,show='headings')
        labels={'Estado':'Etapa del par','Error':'Detalle de error','URL_Resultado':'Página HDOCK','Modelos_Descargados':'Modelos descargados','Carpeta_Modelos':'Carpeta de modelos','Error_Descarga':'Problema al descargar','Ultima_Consulta':'Última consulta'}
        for col in COLUMNS:
            self.tree.heading(col,text=labels.get(col,col)); self.tree.column(col,width=180 if col not in ('URL_Resultado','Carpeta_Modelos') else 340,minwidth=100)
        self.tree.tag_configure('control',background='#fff0cb'); self.tree.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(area,orient='vertical',command=self.tree.yview); vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(area,orient='horizontal',command=self.tree.xview); horizontal.grid(row=1,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.status=tk.StringVar(value='Introduce nombres/genes o UniProt IDs. Las búsquedas ambiguas requieren elección explícita.')
        ttk.Label(self,textvariable=self.status,padding=(20,9),wraplength=1150).pack(fill='x')

    def current_mode(self):
        return 'local' if self.mode.get().startswith('Este equipo') else 'server'

    def mode_changed(self):
        local=self.current_mode()=='local'
        (self.cloud_frame if local else self.local_frame).pack_forget()
        (self.local_frame if local else self.cloud_frame).pack(fill='x',pady=8,after=self.modebar)
        self.run_button.config(text='Calcular pares en este equipo' if local else 'Enviar pares a HDOCK')
        for button in self.cloud_actions: button.config(state='disabled' if local else 'normal')
        self.refresh()

    def guarded(self,operation):
        try:
            return operation()
        except Exception as exc:
            messagebox.showerror('No se pudo continuar',str(exc))

    def set_text(self,text):
        self.editor.delete('1.0','end'); self.editor.insert('1.0',text)

    def load_csv(self):
        path=filedialog.askopenfilename(filetypes=[('CSV','*.csv'),('Todos','*.*')])
        if path:
            self.guarded(lambda:self.set_text(Path(path).read_text(encoding='utf-8-sig')))

    def example(self):
        self.set_text((ROOT/'ejemplo_entrada.csv').read_text(encoding='utf-8-sig'))

    def paste_dialog(self):
        window=tk.Toplevel(self); window.title('Pegar proteínas · una por línea')
        panel=ttk.Frame(window,padding=12); panel.pack(); widgets=[]
        for col,title in enumerate(('Ligandos: UniProt ID, gen o nombre','Receptores: UniProt ID, gen o nombre')):
            ttk.Label(panel,text=title).grid(row=0,column=col)
            widget=tk.Text(panel,width=39,height=12); widget.grid(row=1,column=col,padx=5); widgets.append(widget)
        def add():
            stream=io.StringIO(); writer=csv.writer(stream)
            for kind,widget in zip(('ligando','receptor'),widgets):
                for name in widget.get('1.0','end').splitlines():
                    if name.strip(): writer.writerow([kind,name.strip(),name.strip(),'A' if kind=='receptor' else ''])
            self.editor.insert('end','\n'+stream.getvalue()); window.destroy()
        ttk.Button(panel,text='Añadir al CSV',command=add).grid(row=2,column=0,columnspan=2,pady=8)

    def local_dialog(self):
        def operation():
            items=self.pipeline.config['proteins'] if self.pipeline else read_inputs(self.editor.get('1.0','end'))
            window=tk.Toplevel(self); window.title('Asignar PDB propio')
            keys={protein_label(p):protein_key(p) for p in items}; variable=tk.StringVar(value=protein_label(items[0]))
            ttk.Label(window,text='Selecciona la proteína y su estructura:',padding=10).pack()
            ttk.Combobox(window,textvariable=variable,values=list(keys),state='readonly',width=52).pack(padx=12)
            def assign():
                path=filedialog.askopenfilename(parent=window,filetypes=[('PDB','*.pdb')])
                if not path: return
                key=keys[variable.get()]
                if self.pipeline and key in self.pipeline.config['structures']:
                    messagebox.showinfo('Estructura fijada','Crea un lote nuevo para cambiar una estructura preparada.'); return
                self.local[key]=str(Path(path).resolve())
                if self.pipeline:
                    self.pipeline.config['local_pdb'][key]=self.local[key]; self.pipeline.save()
                self.local_label.config(text=f'PDB propios asignados: {len(self.local)}'); window.destroy()
            ttk.Button(window,text='Elegir PDB…',command=assign).pack(pady=10)
        self.guarded(operation)

    def pick_script(self):
        path=filedialog.askopenfilename(filetypes=[('Python','*.py')])
        if path: self.script.set(path)

    def pick_python(self):
        path=filedialog.askopenfilename(title='Python con pandas y Playwright')
        if path: self.python.set(path)

    def pick_tools(self):
        path=filedialog.askdirectory(title='Carpeta con hdock y createpl')
        if path: self.tool_directory.set(path)

    def local_guide(self):
        window=tk.Toplevel(self); window.title('Instalación del motor local y licencia'); window.geometry('900x650')
        text=tk.Text(window,wrap='word',font=('Segoe UI',11)); text.pack(fill='both',expand=True,padx=12,pady=12)
        text.insert('1.0',(ROOT/'INSTALACION_LOCAL.md').read_text(encoding='utf-8')); text.config(state='disabled')
        ttk.Button(window,text='Abrir licencia oficial',command=lambda:webbrowser.open('https://github.com/huang-laboratory/HDOCKlite/blob/main/LICENSE.txt')).pack(pady=8)

    def check_local(self):
        tools,distribution=self.tool_directory.get(),self.distribution.get()
        def work():
            info=LocalEngine(tools,distribution).check()
            self.events.put({'kind':'message','text':'Motor local disponible: '+str(info)})
        self.run_task(work,'Comprobando WSL y ejecutables…')

    def require_batch(self):
        if self.pipeline is None:
            messagebox.showinfo('Selecciona un lote','Prepara las proteínas o abre un lote guardado.'); return False
        return True

    def prepare(self):
        def operation():
            items=read_inputs(self.editor.get('1.0','end')); taxon=int(self.taxon.get())
            if taxon<=0: raise ValueError('El TaxID debe ser un entero positivo.')
            parent=filedialog.askdirectory(title='Dónde guardar un lote nuevo')
            if not parent: return
            folder=Path(parent)/datetime.now().strftime('lote_%Y%m%d_%H%M%S')
            region='extracellular' if self.region.get().startswith('Región') else 'full'
            self.pipeline=Pipeline.create(folder,items,taxon,dict(self.local),self.dummy.get(),self.email.get().strip(),albumin=self.albumin.get(),region_mode=region)
            self.run_task(lambda:self.pipeline.prepare(self.events.put,self.stop_event),'Descargando y preparando proteínas; todavía no se ejecuta docking…')
        self.guarded(operation)

    def retry_structures(self):
        if self.require_batch(): self.run_task(lambda:self.pipeline.prepare(self.events.put,self.stop_event),'Reintentando preparación fallida…')

    def open_preparation(self):
        if self.require_batch(): self.open_folder(self.pipeline.directory/('prepared' if (self.pipeline.directory/'prepared').exists() else 'structures'))

    def open_batch(self):
        path=filedialog.askdirectory(title='Carpeta que contiene pipeline_config.json')
        if path:
            def operation():
                self.pipeline=Pipeline.load(Path(path)); self.local=dict(self.pipeline.config['local_pdb'])
                engine=self.pipeline.config.get('engine',{})
                self.script.set(engine.get('script',self.script.get())); self.python.set(engine.get('python',self.python.get()))
                self.local_label.config(text=f'PDB propios asignados: {len(self.local)}')
                self.mode.set('Este equipo · HDOCKlite' if self.pipeline.config.get('active_mode')=='local' else 'Servidor HDOCK')
                self.mode_changed(); self.notebook.select(1)
            self.guarded(operation)

    def settings(self):
        count,interval=int(self.model_count.get()),int(self.minutes.get())*60
        if not 1<=count<=20 or not 60<=interval<=3600: raise ValueError('Modelos: 1–20; consulta automática: 1–60 minutos.')
        return count,interval

    def send(self):
        def operation():
            if not self.require_batch(): return
            self.pipeline.verify_structures(); jobs=self.pipeline.config['jobs']
            if not jobs: raise ValueError('No hay pares preparados. Revisa los errores de preparación.')
            count,interval=self.settings(); mode=self.current_mode()
            notifications,automatic=self.notifications.get(),self.auto_monitor.get()
            self.pipeline.config['active_mode']=mode; self.pipeline.save()
            if mode=='local':
                if not self.academic_license.get(): raise ValueError('Revisa la licencia de HDOCKlite antes de ejecutar el modo local.')
                tools,distribution=self.tool_directory.get(),self.distribution.get()
                self.runner=LocalEngine(tools,distribution,self.events.put)
                self.preferences.update(tools=tools,distribution=distribution); write_json(ROOT/'user_settings.json',self.preferences)
                self.pipeline.config.setdefault('local_results',{})
                def work():
                    self.runner.run(jobs,self.pipeline.directory,self.pipeline.config['local_results'],count,self.pipeline.save)
                    if notifications and not self.stop_event.is_set():
                        completed=sum(r.get('state')=='completado' for r in self.pipeline.config['local_results'].values())
                        self.events.put({'kind':'notify','title':'Lote local terminado','text':f'{completed} par(es) con resultados locales. Revisa la tabla y los modelos.'})
                self.run_task(work,'Calculando docking global en este equipo…',mode)
            else:
                script,python,delay,retry=self.script.get().strip(),self.python.get(),float(self.delay.get()),self.retry.get()
                if not Path(script).is_file(): raise ValueError('Selecciona hdock_batch.py instalado.')
                if not 0<=delay<=3600: raise ValueError('Pausa entre envíos inválida.')
                logs=latest_jobs(self.pipeline.directory/'run-log.csv')
                pending=sum(j['jobname'] not in logs or (retry and not accepted(logs[j['jobname']])) for j in jobs)
                if not messagebox.askyesno('Enviar estructuras a HDOCK',f'Se intentarán {pending} pares sin envío aceptado.\nLos PDB saldrán de este equipo hacia HDOCK. Los ya aceptados se conservan.\n¿Iniciar el envío?'): return
                self.pipeline.config['engine']={'script':str(Path(script).resolve()),'python':python,'delay':delay}
                self.pipeline.config['email']=self.email.get().strip()
                for job in jobs: job['email']=self.email.get().strip()
                self.pipeline.save(); self.runner=BatchRunner(script,python,self.pipeline.directory,self.events.put)
                def work():
                    self.runner.run(jobs,delay,retry)
                    if not self.stop_event.is_set():
                        if automatic: start_monitor(self.pipeline.directory,interval,count,notifications)
                        else: self.pipeline.collect(self.events.put,self.stop_event,download_count=count)
                self.run_task(work,'Enviando pares a HDOCK; el cálculo se realiza en el servidor…',mode)
        self.guarded(operation)

    def activate_monitor(self):
        def operation():
            if not self.require_batch(): return
            count,interval=self.settings(); start_monitor(self.pipeline.directory,interval,count,self.notifications.get())
            self.status.set('Seguimiento activado. Continúa con la ventana cerrada mientras el equipo esté encendido y conectado.')
        self.guarded(operation)

    def pause_monitor(self):
        if self.require_batch():
            (self.pipeline.directory/'monitor_stop.request').touch(); self.status.set('Pausa de seguimiento solicitada. Los cálculos ya enviados siguen en HDOCK.')

    def collect(self):
        def operation():
            if not self.require_batch(): return
            count,_=self.settings()
            if running(self.pipeline.directory):
                (self.pipeline.directory/'monitor_refresh.request').touch(); self.status.set('Consulta solicitada al seguimiento activo; no se enviarán nuevos trabajos.'); return
            self.run_task(lambda:self.pipeline.collect(self.events.put,self.stop_event,download_count=count),'Consultando HDOCK y descargando modelos…','server')
        self.guarded(operation)

    def run_task(self,operation,status,mode=None):
        if self.busy: return
        self.busy=True; self.stop_event.clear()
        for button in self.actions: button.config(state='disabled')
        self.mode_combo.config(state='disabled'); self.status.set(status); self.notebook.select(1)
        selected_mode=mode or self.current_mode()
        def worker():
            try:
                operation()
                if self.pipeline: export(self.pipeline.table(selected_mode),self.pipeline.directory/('resumen_local' if selected_mode=='local' else 'resumen'))
            except Exception as exc: self.events.put({'kind':'error','text':str(exc)})
            finally: self.events.put({'kind':'done'})
        threading.Thread(target=worker,daemon=True).start()

    def stop(self):
        self.stop_event.set()
        if self.runner: self.runner.stop()
        self.status.set('Se pausará después del par activo. No cancela cálculos ya aceptados por HDOCK.')

    def log(self,text):
        self.console.config(state='normal'); self.console.insert('end',text+'\n'); self.console.see('end'); self.console.config(state='disabled')

    def show_notification(self,title,text):
        ok,error=notify(title,text)
        self.log('Notificación solicitada a Windows.' if ok else 'No se pudo solicitar la notificación: '+error)

    def test_notification(self):
        self.show_notification('Prueba de Docking Matrix','Las notificaciones avisarán cuando haya resultados disponibles.')

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait(); kind=event['kind']
                if kind in ('message','error'):
                    self.log(event['text'])
                    if kind=='error': messagebox.showerror('No se pudo completar la operación',event['text'])
                elif kind=='job':
                    row=event['row']; self.log(f"{row['jobname']} | token={row.get('token','')} | {row.get('error','')}"); self.refresh()
                elif kind=='local_job': self.log(event['name']+': '+event['result']['state']); self.refresh()
                elif kind=='result_ready':
                    if self.notifications.get(): self.show_notification('Resultado de HDOCK disponible',event['name']+': score disponible; revisa los modelos.')
                    self.refresh()
                elif kind=='notify': self.show_notification(event['title'],event['text'])
                elif kind=='done':
                    self.busy=False
                    for button in self.actions: button.config(state='normal')
                    self.mode_combo.config(state='readonly'); self.status.set('Operación terminada. Revisa los contadores y cualquier detalle de error.'); self.mode_changed()
        except queue.Empty: pass
        if self.pipeline and not self.busy and time.monotonic()-self.last_refresh>5:
            self.refresh(); self.last_refresh=time.monotonic()
        self.after(200,self.poll)

    def filtered(self):
        frame=self.pipeline.table(self.current_mode())
        return frame[frame['Categoria_Receptor']==self.category.get()] if self.category.get()!='Todas' else frame

    def refresh(self):
        if not self.pipeline: return
        import pandas as pd
        frame=self.pipeline.table(self.current_mode()); logs=latest_jobs(self.pipeline.directory/'run-log.csv')
        sent=sum(accepted(logs.get(j['jobname'],{})) for j in self.pipeline.config['jobs']); ready=int(frame['Docking_Score'].notna().sum())
        errors=len(self.pipeline.config['errors'])+int(frame['Estado'].str.startswith('error').sum())
        engine_label='local' if self.current_mode()=='local' else 'HDOCK'
        self.counts.set(f"Proteínas listas: {len(self.pipeline.config['structures'])} | Pares preparados: {len(frame)} | Pares enviados a HDOCK: {sent}\nResultados listos ({engine_label}): {ready} | Modelos descargados: {int(frame['Modelos_Descargados'].sum())} | Errores: {errors} | Pares omitidos: {len(self.pipeline.config.get('skipped_pairs',[]))}")
        self.progress.config(maximum=max(1,len(frame)),value=ready); self.batch_label.config(text='Lote: '+str(self.pipeline.directory))
        path=self.pipeline.directory/'monitor_state.json'
        if path.exists():
            try:
                state=json.loads(path.read_text(encoding='utf-8'))
                self.monitor_status.set(f"Seguimiento HDOCK: {state.get('status','')} · Última consulta: {state.get('updated_at','')}" + (' · Aviso: '+state['notification_error'] if state.get('notification_error') else ''))
            except (ValueError,OSError): pass
        selected=self.tree.selection(); self.tree.delete(*self.tree.get_children())
        for _,row in self.filtered().iterrows():
            values=['' if pd.isna(row[col]) else row[col] for col in COLUMNS]; values[COLUMNS.index('Estado')]=STATE_LABELS.get(row['Estado'],row['Estado'])
            self.tree.insert('','end',iid=row['Jobname'],values=values,tags=('control',) if row['Categoria_Receptor']=='control' else ())
        for name in selected:
            if self.tree.exists(name): self.tree.selection_add(name)

    def selected_row(self):
        selection=self.tree.selection()
        if not selection: messagebox.showinfo('Selecciona un par','Haz clic en una fila de la tabla.'); return None
        frame=self.filtered(); return frame[frame['Jobname']==selection[0]].iloc[0]

    def export_view(self):
        if self.require_batch():
            path=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='resultados.csv',filetypes=[('CSV y Excel','*.csv')])
            if path: self.guarded(lambda:export(self.filtered(),Path(path)))

    def open_result(self):
        if not self.require_batch(): return
        row=self.selected_row()
        if row is not None:
            from urllib.parse import urlparse
            url=row['URL_Resultado']
            if urlparse(url).hostname=='hdock.phys.hust.edu.cn': webbrowser.open(url)
            else: messagebox.showinfo('Resultado local','Este cálculo no tiene una página HDOCK. Abre su carpeta de modelos.')

    def open_folder(self,path):
        path=Path(path).resolve()
        if not path.exists(): messagebox.showinfo('Todavía no disponible',str(path)); return
        if os.name=='nt': os.startfile(str(path))
        else: subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(path)])

    def open_models(self):
        if self.require_batch():
            row=self.selected_row()
            if row is not None:
                if row['Carpeta_Modelos']: self.open_folder(row['Carpeta_Modelos'])
                else: messagebox.showinfo('Modelos pendientes','Consulta y descarga los resultados primero.')

    def open_viewer(self):
        if not self.require_batch(): return
        row=self.selected_row()
        if row is None or not row['Carpeta_Modelos']: return
        directory=Path(row['Carpeta_Modelos']); files=sorted(directory.glob('modelo_*_visor.pdb'),key=lambda p:int(p.name.split('_')[1]))
        if not files: messagebox.showinfo('Sin modelos','No hay PDB descargados para este par.'); return
        executable=self.preferences.get('viewer','')
        if not Path(executable).is_file():
            candidate=Path('C:/Program Files/ChimeraX 1.12/bin/ChimeraX.exe')
            executable=str(candidate) if candidate.is_file() else filedialog.askopenfilename(title='Selecciona PyMOL o ChimeraX')
        if executable:
            self.preferences['viewer']=executable; write_json(ROOT/'user_settings.json',self.preferences)
            subprocess.Popen([executable,str(files[0])],cwd=str(directory))

    def close_app(self):
        if self.busy: messagebox.showinfo('Par activo','Pulsa «Pausar tras el par activo» y espera antes de cerrar para conservar el resultado o token.')
        else: self.destroy()


if __name__=='__main__':
    App().mainloop()
