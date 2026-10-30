# Docking Matrix: proteína–proteína

Aplicación de escritorio en Python 3.9+ y Tkinter para preparar una matriz RBP × receptor, delegar envíos a HDOCK mediante `hdock_batch` y exportar resultados a CSV/Excel. Interfaz y comentarios en español.

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

Conserva el script externo separado. La aplicación lo invoca mediante `subprocess`, con argumentos separados, sin `shell=True`, así:

```text
python hdock_batch.py jobs.csv --out directorio -j 1
```

Puedes usar otro entorno: selecciona su ejecutable Python en la pestaña de seguimiento. Debe tener pandas, Playwright y Chromium instalados. Un único envío simultáneo y una pausa configurable reducen carga y aíslan fallos. El script externo controla su formulario y la captura del token; esta aplicación no implementa la sumisión HTTP.

## 3. Preparar la entrada

Carga `ejemplo_entrada.csv`, edita el CSV en pantalla o pega listas (un identificador por línea) mediante «Añadir listas pegadas».

```csv
tipo,identificador,nombre_comun,categoria
RBP,P09651,HNRNPA1,
RBP,P22626,HNRNPA2B1,
receptor,P00533,EGFR,A
receptor,P04626,ERBB2,B
receptor,P08581,MET,C
```

- `tipo`: RBP o receptor. `categoria`: A/B/C para candidatos, `control` para controles personalizados. Se preservan como filas independientes.
- `identificador`: accession UniProt o símbolo exacto del gen. Los nombres de genes se resuelven con UniProt REST y el TaxID visible en pantalla (9606 humano por defecto), priorizando entradas curadas (`reviewed:true`); si no hay ninguna, se buscan también las no curadas. Si hay varias coincidencias en la búsqueda utilizada se exige un accession; no se elige una proteína arbitrariamente.
- Los duplicados exactos se eliminan por tipo/identificador; los metadatos contradictorios se rechazan. Dos alias que resuelvan al mismo accession se deben unificar en la entrada antes de preparar el lote.
- Descarga: `https://alphafold.ebi.ac.uk/api/prediction/{accession}` → `pdbUrl`. Si hay varios modelos, se requiere elección mediante PDB local para no tomar un fragmento arbitrario.
- «Asignar PDB local» permite reemplazar la descarga para una proteína. Ante un fallo abre esta opción después de preparar y pulsa «Revisar estructuras pendientes».
- La comprobación PDB verifica registros ATOM y coordenadas finitas; no corrige cadenas, hidrógenos, protonación, dominios ni regiones desordenadas. Prepara las estructuras apropiadas antes del envío.

Los ejemplos sólo ilustran el formato; no constituyen una hipótesis de interacción validada.

## 4. Ejecutar

```powershell
.venv\Scripts\python app.py
```

También puedes abrir `ejecutar.bat` en Windows tras instalar dependencias.

Si tu red usa una CA institucional y aparece `CERTIFICATE_VERIFY_FAILED`, configura `REQUESTS_CA_BUNDLE` con el archivo PEM de CA aprobado por tu institución. Conserva la verificación TLS; no uses `verify=False`.

1. Carga las proteínas, elige organismo y asigna PDB locales si corresponde.
2. Pulsa «Crear lote y preparar estructuras» y elige una carpeta. Se crea un subdirectorio fechado. Las descargas no envían nada a HDOCK.
3. Revisa el registro, la cantidad de pares y `pares_omitidos.csv`. Si una estructura falla, se conservan las otras y se omiten únicamente los pares afectados.
4. En «Lote y seguimiento» selecciona `hdock_batch.py` y su Python.
5. Pulsa «Enviar pendientes». La aplicación indica el destino y pide iniciar la transferencia de los PDB. Los datos se procesan en un servidor externo.
6. El registro muestra mensajes, errores y tokens. **Enviado** significa que existe un token, no que el cálculo haya terminado. La barra cuenta pares con score disponible.
7. Al acabar los envíos se consulta cada URL una vez. Si HDOCK sigue procesando, usa «Actualizar resultados» más tarde. No se consulta continuamente en segundo plano.
8. En «Resultados» filtra A/B/C/control, abre un enlace y exporta la vista. Cada fase guarda además `resumen.csv` y `resumen.xlsx` con la tabla completa.

## 5. Controles e interpretación

Se añade automáticamente albúmina bovina UniProt **P02769** como control de referencia provisional; el usuario puede añadir ubiquitina **PDB 1UBQ** o sus propios controles. Para cambiar el predeterminado edita `CONTROL` en `pipeline.py`. Se aplica exactamente el mismo motor y configuración de envío a todos los pares.

**No hay una proteína universalmente negativa.** Albúmina y ubiquitina pueden interactuar con algunas RBPs; su condición negativa debe justificarse para la hipótesis concreta. Compartir el protocolo no elimina diferencias por tamaño, dominios, calidad estructural o composición superficial. El score de HDOCK se usa para ordenar este cribado exploratorio; no es una energía libre experimental, una medida directa de afinidad ni una demostración de interacción. Un control positivo conocido y validación experimental mejoran la interpretación.

## 6. Archivos y reanudación

Cada lote conserva:

| Archivo | Contenido |
| --- | --- |
| `pipeline_config.json` | Entrada, TaxID, controles, fecha UTC, rutas, fuentes, SHA-256 de PDB y motor, pares, errores y scores |
| `structures/` | Copias de los PDB utilizados |
| `jobs.csv` | `receptor_pdb,ligand_pdb,jobname,email` para el lote preparado |
| `pares_omitidos.csv` | Pares que no pudieron prepararse y motivo |
| `run-log.csv` | Bitácora acumulada compatible con el formato del motor |
| `attempts/` | CSV, salida de consola y bitácora de cada intento individual |
| `reports/` | HTML de las páginas consultadas como evidencia del score |
| `resumen.csv` / `resumen.xlsx` | Tabla ordenada; controles resaltados y filtro en Excel |

La tabla contiene `RBP, Receptor, Categoria_Receptor, Docking_Score, Job_Token, URL_Resultado`, más `Estado, Error, Jobname` para trazabilidad. Se usa el menor valor numérico **de la columna explícita Docking Score** entre los modelos presentes en la página. Si falta la tabla o el servidor cambió su HTML, el score queda vacío con estado `pendiente_o_formato_desconocido`; abre la URL para distinguir ambos casos. No se confunde RMSD/confianza con docking score. Errores de consulta quedan como `error_consulta` y se pueden volver a consultar.

Para reanudar, elige «Abrir lote / reanudar» y selecciona la carpeta con su configuración y `run-log.csv`. Se omiten los envíos aceptados, incluso si todavía no tienen score. La correspondencia usa `jobname` estable, no el número de fila que cambia al filtrar CSV. No se reintentan errores de envío automáticamente: revisa sus registros y marca «Reintentar envíos fallidos ya revisados». Un envío podría haber llegado al servidor aunque el script no capturase su token.

Si se interrumpe el proceso en medio de un envío, `submission-in-flight.json` conserva el intento. Al abrir de nuevo se recupera su token si aparece en la bitácora de ese intento; de lo contrario se bloquean nuevos envíos hasta conciliar. Revisa `attempts/.../console.log` y HDOCK; añade el registro recuperado a `run-log.csv` o archiva el marcador si verificaste que no se envió. No se promete exactamente una entrega frente a cortes de red: el servidor externo no ofrece aquí una clave de idempotencia.

«Detener al acabar el par» espera el proceso activo para conservar el token. No cancela cálculos que ya estén ejecutándose en HDOCK. No cambies estructuras o borres bitácoras del lote; una huella diferente exige un lote nuevo. Las rutas son absolutas: mantén la carpeta en su ubicación original.

No se suben al repositorio los lotes, correos, estructuras ni resultados: están excluidos de Git por defecto. La visibilidad del repositorio se mantiene privada hasta que su propietario decida cambiarla.

## 7. Desarrollo y pruebas

```powershell
.venv\Scripts\python -m unittest -v
```

Las pruebas cubren matriz/controles, errores parciales, resolución ambigua, estructuras, columnas de score, exportación y ejecución real de un subproceso simulado con reanudación. No envían trabajos reales ni constituyen validación científica. La GUI utiliza un hilo de trabajo y una cola; sólo el hilo principal modifica Tkinter.

Módulos editables: `data_fetcher.py` (UniProt/AlphaFold/PDB), `pipeline.py` (matriz y persistencia), `job_runner.py` (motor externo), `results_parser.py` (scores y exportación), `app.py` (interfaz).

## Fuentes y límites de integración

- Motor, esquema y CLI: https://github.com/SidSin0809/hdock_batch
- API AlphaFold: https://alphafold.ebi.ac.uk/api-docs
- UniProt: https://www.uniprot.org/help/api_queries
- Estructura 1UBQ: https://www.rcsb.org/structure/1UBQ
- HDOCK: http://hdock.phys.hust.edu.cn/

El adaptador depende del sitio y del motor externos. `hdock_batch` usa actualmente HTTP para el servidor; no aporta cifrado del transporte en ese endpoint. No se incluye ni modifica su código. No se requieren credenciales HDOCK en esta aplicación y no se garantiza autenticación adicional del servidor. Si el formulario cambia, puede ser necesario actualizar el motor externo. No se han enviado trabajos reales como parte de las pruebas iniciales.
