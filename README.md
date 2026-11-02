# Docking Matrix: proteína–proteína

Aplicación de escritorio en Python 3.9+ y Tkinter para preparar una matriz ligando × receptor, delegar envíos a HDOCK mediante `hdock_batch` y exportar resultados a CSV/Excel. Ambos participantes son proteínas. Interfaz y comentarios en español.

La versión actual ofrece también **cálculo local con HDOCKlite (Linux/WSL)**, preparación estructural trazable, descarga de modelos, apertura en PyMOL/ChimeraX y seguimiento automático con avisos de escritorio. Para el modo local lee [INSTALACION_LOCAL.md](INSTALACION_LOCAL.md). Los resultados de los dos motores se mantienen separados.

La versión 0.4.0 añade **⚙ Configuración** para ordenar y activar fuentes gratuitas: AlphaFold DB, PDB/PDBe, SWISS-MODEL Repository y ESMFold. Consulta [CONFIGURACION_PROVEEDORES.md](CONFIGURACION_PROVEEDORES.md) para prioridad, caché, respaldo tras errores temporales y procedencia. [ESTRUCTURAS_ALTERNATIVAS.md](ESTRUCTURAS_ALTERNATIVAS.md) describe validación, CSV `pdb_local`, privacidad y CLI. No se cambian los PDB ni tokens de los lotes existentes.

## 1. Instalación

Instala Python 3.9 o posterior desde https://www.python.org/downloads/ con Tkinter. En Windows comprueba `py -3 --version`; algunos equipos tienen un `python` antiguo de MGLTools. En Linux puede ser necesario instalar el paquete `python3-tk`.

```powershell
git clone https://github.com/mortismain777-spec/docking-proteina-a-proteina.git
cd docking-proteina-a-proteina
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

En macOS/Linux sustituye `py -3` por `python3` y `.venv\Scripts\python` por `.venv/bin/python`.

## 2. Instalar el motor externo

Clona el repositorio **hdock_batch** con guion bajo. La documentación upstream menciona un guion y un `requirements.txt` que no estaban en el árbol consultado; estos comandos usan el repositorio y dependencias reales:

```powershell
git clone https://github.com/SidSin0809/hdock_batch.git
.venv\Scripts\python -m pip install pandas playwright
.venv\Scripts\python -m playwright install chromium
```

Si el proceso no encuentra Chromium en la caché del usuario, puedes instalarlo dentro del proyecto:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
.venv\Scripts\python -m playwright install --only-shell chromium
```

Cuando existe `.playwright-browsers`, el adaptador establece esa ruta explícitamente al invocar el motor. El directorio está excluido de Git. Tras cambiar el adaptador, cierra y abre la aplicación y usa «Abrir lote / reanudar» para conservar el lote existente.

Conserva el script externo separado. La aplicación lo invoca mediante `subprocess`, con argumentos separados, sin `shell=True`, así:

```text
python hdock_batch.py jobs.csv --out directorio -j 1
```

Puedes usar otro entorno: selecciona su ejecutable Python en la pestaña de seguimiento. Debe tener pandas, Playwright y Chromium instalados. Un único envío simultáneo y una pausa configurable reducen carga y aíslan fallos. El script externo controla su formulario y la captura del token; esta aplicación no implementa la sumisión HTTP.

## 3. Preparar la entrada

Carga `ejemplo_entrada.csv`, edita el CSV en pantalla o pega listas (un identificador por línea) mediante «Añadir listas pegadas».

```csv
tipo,identificador,nombre_comun,categoria
ligando,P09651,HNRNPA1,
ligando,P22626,HNRNPA2B1,
receptor,P00533,EGFR,A
receptor,P04626,ERBB2,B
receptor,P08581,MET,C
```

- `tipo`: `ligando` o `receptor`. `categoria`: A/B/C para receptores candidatos, `control` para controles personalizados; dejar vacía para ligandos. Se preservan como filas independientes. Los CSV antiguos con `RBP` siguen aceptándose como equivalentes de `ligando`, sin distinguir mayúsculas y minúsculas.
- `identificador`: accession UniProt, símbolo exacto del gen o nombre de proteína. Se resuelve con UniProt REST y el TaxID visible (9606 humano por defecto), priorizando entradas curadas. Un nombre con múltiples coincidencias exige un accession; no se elige una proteína arbitrariamente. «Pegar listas de proteínas» permite introducir un nombre/ID por línea y construir el CSV automáticamente.
- Los duplicados exactos se eliminan por tipo/identificador; los metadatos contradictorios se rechazan. Dos alias que resuelvan al mismo accession se deben unificar en la entrada antes de preparar el lote.
- Descarga: `https://alphafold.ebi.ac.uk/api/prediction/{accession}` → `pdbUrl`. Se selecciona el accession exacto solicitado, excluyendo otras isoformas. Si quedan varios modelos del mismo accession, se requiere elección mediante PDB local para no tomar un fragmento arbitrario.
- «Asignar PDB local» permite reemplazar la descarga para una proteína. Ante un fallo abre esta opción después de preparar y pulsa «Revisar estructuras pendientes».
- La preparación conserva el original en `structures/` y genera átomos pesados en `prepared/`: retira aguas/HETATM e hidrógenos, elige un conformero alternativo por ocupación y permite seleccionar cadenas. Registra geometría, SHA-256, advertencias de esqueleto incompleto y estadísticas de pLDDT cuando proceden de AlphaFold. No reconstruye residuos, añade glicanos ni realiza minimización o protonación específica.

Los ejemplos sólo ilustran el formato; no constituyen una hipótesis de interacción validada.

Opcionalmente el CSV puede incluir `residuo_inicio,residuo_fin`: enteros positivos, ambos presentes, para recortar una región tras descargar AlphaFold o copiar un PDB local. La estructura debe cubrir todos los residuos del intervalo en una sola cadena sin inserciones. Se conserva la numeración y las coordenadas; no se añaden glicanos ni se optimiza la estructura. El rango debe justificarse con anotaciones o el experimento de referencia. La configuración registra el rango y las huellas del archivo completo y el recortado. Cambiar el rango de un lote preparado exige crear un lote nuevo.

También admite `cadenas` (por ejemplo `A` o `"A,B"`). En pantalla puedes elegir «Región extracelular anotada en UniProt»: sólo se selecciona automáticamente si hay una única región inequívoca y no proporcionaste ya un rango. El modo de búsqueda del motor local es global ab initio, sin grid box manual. La caja geométrica del informe sólo describe la estructura: no limita la búsqueda.

## 4. Ejecutar

```powershell
.venv\Scripts\python app.py
```

También puedes abrir `ejecutar.bat` en Windows tras instalar dependencias.

Si tu red usa una CA institucional y aparece `CERTIFICATE_VERIFY_FAILED`, configura `REQUESTS_CA_BUNDLE` con el archivo PEM de CA aprobado por tu institución. Conserva la verificación TLS; no uses `verify=False`.

1. Carga las proteínas, elige organismo y asigna PDB locales si corresponde.
2. Pulsa «Preparar proteínas y crear pares» y elige una carpeta. Se crea un subdirectorio fechado. Este paso no calcula docking ni envía nada a HDOCK.
3. Revisa el registro, la cantidad de pares y `pares_omitidos.csv`. Si una estructura falla, se conservan las otras y se omiten únicamente los pares afectados.
4. En «Ejecución y seguimiento» elige «Servidor HDOCK» y comprueba `hdock_batch.py` y su Python; o «Este equipo · HDOCKlite» tras instalar el motor local.
5. En modo servidor pulsa «Enviar pares a HDOCK». La confirmación indica cuántos pares se intentarán; no se repiten los aceptados. En modo local pulsa «Calcular pares en este equipo».
6. El registro muestra mensajes, errores y tokens. **Enviado** significa que existe un token, no que el cálculo haya terminado. La barra cuenta pares con score disponible.
7. El seguimiento automático está activado por defecto: consulta cada 5 minutos, descarga 5 modelos por par y solicita un aviso de Windows al aparecer un score. Puedes ajustar intervalo (1–60 min) y modelos (1–20). «Consultar HDOCK y descargar modelos» solicita una revisión inmediata, sin reenviar trabajos.
8. En «Resultados y modelos» filtra A/B/C/control, abre la carpeta/modelo y exporta la vista. «Etapa del par» describe progreso; «Detalle de error» explica fallos; «Última consulta» es una fecha. Los contadores distinguen proteínas, pares preparados, pares enviados a HDOCK y resultados listos.

## Seguimiento y modelos

El monitor es un proceso local independiente. Se inicia después del envío si la opción automática está marcada; para lotes ya enviados utiliza «Activar seguimiento en segundo plano». Continúa si cierras la ventana, mientras Windows permanezca encendido, conectado y sin suspender. No puede notificar con el equipo apagado y no se instala como servicio ni tarea al inicio de Windows. Tras reiniciar, abre el lote y reactiva el seguimiento. Se detiene al completar los modelos de los pares aceptados, al pausarlo o tras 48 horas.

Los avisos se solicitan una sola vez por resultado/token y no se envían durante la espera. La visualización depende de la configuración de notificaciones/No molestar de Windows. «Probar notificación» permite comprobarlo. Si falla la API, se registra el motivo; no se declara que el aviso se mostró.

Se descargan los enlaces oficiales a `model_1.pdb` y siguientes que ofrece la página; se excluye el modelo 0 de homología de la selección de modelos de docking. Se conservan los PDB originales y copias `_visor.pdb` con identificadores de cadena diferenciados, sin mover coordenadas, además de SHA-256 y procedencia. Las carpetas incluyen sesiones `abrir_chimerax.cxc` y `abrir_pymol.pml`; ábrelas desde su carpeta de modelos. «Abrir mejor modelo en visor» abre el modelo 1 en ChimeraX o el visor seleccionado. Los errores al descargar no eliminan un score ya disponible.

El monitor escribe `monitor_state.json`, `monitor.log` y `resumen_hdock_auto.*`; la GUI incorpora esos resultados sin que el monitor sobrescriba su configuración. Una exclusión por archivo impide duplicar monitores para el mismo lote. «Pausar seguimiento» deja de consultar, pero no cancela trabajos de HDOCK.

## 5. Controles e interpretación

En los lotes nuevos de la interfaz, albúmina bovina UniProt **P02769** y ubiquitina **PDB 1UBQ** son referencias opcionales, desmarcadas por defecto. Los controles experimentales se incluyen como receptores de categoría `control` en el CSV. Los lotes anteriores conservan los participantes que ya tenían. Se aplica el mismo motor y configuración de envío a todos los pares.

La etiqueta `control` no certifica experimentalmente una proteína: guarda la publicación, especie, constructos y condiciones que respaldan esa elección. Para reproducir un ensayo deben considerarse también modificaciones, glicanos, fusión a etiquetas y presentación de las proteínas.

**No hay una proteína universalmente negativa.** Albúmina y ubiquitina pueden interactuar con algunas proteínas utilizadas como ligandos; su condición negativa debe justificarse para la hipótesis concreta. Compartir el protocolo no elimina diferencias por tamaño, dominios, calidad estructural o composición superficial. El score de HDOCK se usa para ordenar este cribado exploratorio; no es una energía libre experimental, una medida directa de afinidad ni una demostración de interacción. Un control positivo conocido y validación experimental mejoran la interpretación.

## 6. Archivos y reanudación

Cada lote conserva:

| Archivo | Contenido |
| --- | --- |
| `pipeline_config.json` | Entrada, TaxID, controles, fecha UTC, rutas, fuentes, SHA-256 de PDB y motor, pares, errores y scores |
| `structures/` | Copias de los PDB utilizados |
| `prepared/` | Copias de trabajo e informes de preparación |
| `jobs.csv` | `receptor_pdb,ligand_pdb,jobname,email` para el lote preparado |
| `pares_omitidos.csv` | Pares que no pudieron prepararse y motivo |
| `run-log.csv` | Bitácora acumulada compatible con el formato del motor |
| `attempts/` | CSV, salida de consola y bitácora de cada intento individual |
| `reports/` | HTML de las páginas consultadas como evidencia del score |
| `models/` | Modelos HDOCK originales, copias para visor, sesiones y procedencia |
| `local/` | Ejecuciones HDOCKlite, comandos, estructuras, consola y modelos |
| `monitor_state.json` | Resultados y avisos del seguimiento independiente |
| `resumen.csv` / `resumen.xlsx` | Tabla ordenada; controles resaltados y filtro en Excel |

La tabla conserva las columnas originales y añade `Motor, Modelos_Descargados, Carpeta_Modelos, Error_Descarga, Ultima_Consulta`. Se usa el menor valor numérico rotulado **Docking Score** en la página. Si no hay tabla, queda vacío. No se confunde RMSD/confianza con docking score. El modo local no utiliza tokens/URLs del servidor y se exporta por separado en `resumen_local.*`.

Los lotes anteriores que guardaban `RBP` se abren sin perder estructuras, tokens ni scores. Las nuevas vistas y exportaciones muestran `Ligando`; se conservan los prefijos internos históricos de las claves y los `jobname` para que el cambio de etiqueta no cause envíos duplicados. Los CSV/Excel exportados anteriormente no se modifican; para obtener la nueva cabecera, vuelve a exportar desde la aplicación.

El lector admite el formato real de HDOCK con `Docking Score` como fila. Si actualizaste el programa, reinicia la ventana, abre el lote y pulsa «Consultar HDOCK y descargar modelos»; no vuelvas a enviar los pares.

Para reanudar, elige «Abrir lote guardado» y selecciona la carpeta con su configuración y `run-log.csv`. Se omiten los envíos aceptados aunque no tengan score. No se reintentan errores automáticamente: revisa sus registros y marca la casilla de reintento. Los lotes históricos no se preparan de nuevo ni cambian sus `jobname`; para aplicar la preparación nueva crea otro lote. No se asume que un envío sin token nunca llegó al servidor.

Si se interrumpe el proceso en medio de un envío, `submission-in-flight.json` conserva el intento. Al abrir de nuevo se recupera su token si aparece en la bitácora de ese intento; de lo contrario se bloquean nuevos envíos hasta conciliar. Revisa `attempts/.../console.log` y HDOCK; añade el registro recuperado a `run-log.csv` o archiva el marcador si verificaste que no se envió. No se promete exactamente una entrega frente a cortes de red: el servidor externo no ofrece aquí una clave de idempotencia.

«Pausar tras el par activo» espera el proceso activo para conservar token o resultado local. No cancela cálculos de HDOCK. No cambies estructuras o borres bitácoras del lote; una huella diferente exige un lote nuevo. Las rutas son absolutas: mantén la carpeta en su ubicación original.

No se suben al repositorio los lotes, correos, estructuras ni resultados: están excluidos de Git por defecto. La visibilidad del repositorio se mantiene privada hasta que su propietario decida cambiarla.

## 7. Desarrollo y pruebas

```powershell
.venv\Scripts\python -m unittest -v
```

Las pruebas cubren matriz/controles, errores parciales, resolución ambigua, estructuras, columnas de score, exportación y ejecución real de un subproceso simulado con reanudación. No envían trabajos reales ni constituyen validación científica. La GUI utiliza un hilo de trabajo y una cola; sólo el hilo principal modifica Tkinter.

Módulos: `data_fetcher.py` (búsqueda/descarga), `preparation.py` (preparación), `pipeline.py` (matriz/persistencia), `job_runner.py` (envíos), `local_engine.py` (HDOCKlite/WSL), `results_parser.py` (scores/exportación), `model_files.py` (PDB/visores), `result_monitor.py` (seguimiento), `desktop_notify.py` (avisos), `app.py` (interfaz).

## Fuentes y límites de integración

- Motor, esquema y CLI: https://github.com/SidSin0809/hdock_batch
- API AlphaFold: https://alphafold.ebi.ac.uk/api-docs
- UniProt: https://www.uniprot.org/help/api_queries
- Estructura 1UBQ: https://www.rcsb.org/structure/1UBQ
- HDOCK: http://hdock.phys.hust.edu.cn/

El adaptador depende del sitio y del motor externos. `hdock_batch` usa actualmente HTTP para el servidor; no aporta cifrado del transporte en ese endpoint. No se incluye ni modifica su código. No se requieren credenciales HDOCK en esta aplicación y no se garantiza autenticación adicional del servidor. Si el formulario cambia, puede ser necesario actualizar el motor externo. No se han enviado trabajos reales como parte de las pruebas iniciales.
