# Obtención alternativa de estructuras — versión 0.4.0

[English](ESTRUCTURAS_ALTERNATIVAS.en.md) | **Español** · [Guía principal](README.es.md)

La prioridad es configurable desde **⚙ Configuración**, incluyendo PDB y SWISS-MODEL Repository. Consulta [CONFIGURACION_PROVEEDORES.md](CONFIGURACION_PROVEEDORES.md) para la política completa; los lotes anteriores conservan sus opciones hasta que se cambien explícitamente.

## Uso desde la aplicación

1. Cierra y abre Docking Matrix mediante el acceso directo del escritorio. Los trabajos aceptados por HDOCK continúan en el servidor.
2. Introduce nombres/genes con organismo o accesiones UniProt/RefSeq. Los nombres ambiguos requieren una accession; no se elige una proteína al azar. Las versiones RefSeq se conservan. La selección automática de región extracelular requiere una entrada UniProt con anotación inequívoca; para RefSeq utiliza un rango explícito.
3. Mantén marcada **Permitir fuentes alternativas según Configuración** para habilitar respaldos. Desactiva ESMFold en Configuración si no autorizas transmitir secuencias a ese servidor. La casilla general está activada por defecto para lotes nuevos.
4. Pulsa **Preparar proteínas y crear pares**. La consola muestra la fuente por proteína y la barra cuenta el avance durante la preparación. Un fallo sólo omite los pares afectados.
5. Abre **Ver informe de preparación**: la carpeta del lote contiene `structure_report.csv`, `needs_manual_modeling.txt` e informes individuales bajo `prepared/`.
6. Los resultados añaden `Fuente_Ligando`, `Fuente_Receptor`, `pLDDT_Ligando` y `pLDDT_Receptor`; se conservan las columnas anteriores y los controles.

Para reanudar abre el lote guardado y pulsa **Reintentar preparación que falló**. La casilla aplica a los intentos nuevos; no reemplaza estructuras ya preparadas. Los lotes históricos se abren con fallback desactivado hasta que lo actives expresamente. Para cambiar una proteína o un modelo ya utilizado, crea otro lote.

## Prioridad y errores

1. PDB seleccionado mediante la interfaz o columna `pdb_local`. La selección de la interfaz tiene prioridad si también se indicó un archivo en CSV.
2. Caché validada, si está activada la opción de usarla antes de consultar fuentes, respetando las fuentes activas y su orden. Sin fallback, sólo se reutiliza automáticamente caché de AlphaFold. Consulta la guía de configuración para la política completa.
3. Consultar fuentes activas según el orden del lote: por defecto AlphaFold DB, PDB/PDBe, SWISS-MODEL Repository y ESMFold. AlphaFold conserva selección canónica, comprobación de fragmentos y recorte existentes.
4. Si una fuente no ofrece un modelo utilizable, pasar a la siguiente. Los errores temporales permiten continuar sólo si la opción correspondiente está activada. Un 404 en un enlace PDB no se interpreta como ausencia en AlphaFold. Las respuestas ambiguas no se resuelven eligiendo un fragmento arbitrario.
5. Las accesiones RefSeq/GenBank de proteína reconocidas no son claves de AlphaFold: si el fallback está permitido se obtiene FASTA de NCBI y se utiliza ESMFold. No es necesario que tengan equivalencia UniProt. Se rechazan entradas sin una secuencia única de aminoácidos estándar.
6. Si no es posible obtener un modelo, registrar el motivo y continuar. `RETRY_PENDING` distingue una consulta temporalmente fallida de la necesidad de modelado manual; `INPUT_ERROR` identifica respuestas HTTP 400.

AlphaFold y la resolución UniProt conservan tres intentos GET totales mediante el adaptador existente. Para FASTA y ESMFold se hacen **tres intentos totales**, con esperas de 2 y 4 segundos para 429/500/502/503/504, conexión o timeout. Se respeta un `Retry-After` mayor, expresado en segundos o fecha HTTP. No se reintentan errores de entrada ni errores permanentes. Se espera al menos un segundo entre inicios consecutivos de llamadas al mismo servicio de la cascada FASTA/ESMFold. El POST de predicción tiene timeout de lectura de 300 segundos por intento. Un timeout de POST no garantiza que el servicio no haya comenzado a calcular.

**Detener preparación** interrumpe las esperas y evita iniciar la siguiente proteína. Una petición síncrona ya iniciada puede tardar hasta su timeout; no se promete cancelación instantánea del servidor. Lo completado se conserva en la configuración y el reporte. `run-log.csv` sigue siendo exclusivamente la bitácora de envíos de docking; no se escribe durante la preparación.

## Caché y PDB locales

No es necesario crear `pdb_cache/`: se crea automáticamente junto al proyecto para lotes nuevos. Los JSON sidecar actúan como índice offline. La identidad incluye identificador resuelto, identificador original, organismo, SHA-256 de la secuencia efectivamente representada, rango, cadenas y fuente. El nombre es el SHA-256 de esa identidad; no se usa el identificador como ruta. Los archivos contienen hashes del PDB y metadatos. Se verifican coordenadas, residuos Cα, modelo único, secuencia/hash y parámetros antes de reutilizar. Una entrada corrupta se ignora.

No coloques un PDB suelto en la caché esperando que se infiera su identidad. Usa **Asignar PDB propio** o `pdb_local`; así se valida y registra explícitamente. Los modelos locales se archivan en caché con su procedencia, pero no se reutilizan automáticamente para otro lote sin una selección explícita del usuario. No se sustituye un archivo manual nuevo por una copia antigua.

El CSV antiguo de cuatro columnas sigue funcionando. `ejemplo_entrada.csv` incluye `pdb_local` vacío. Al cargar un CSV desde archivo, las rutas relativas se resuelven respecto a su carpeta; al pegar texto utiliza rutas absolutas. Las columnas `residuo_inicio,residuo_fin,cadenas` siguen siendo opcionales.

## Predicción, dominios y confianza

El endpoint documentado por los autores es `https://api.esmatlas.com/foldSequence/v1/pdb/`. Se comprobó un POST real con una secuencia pública, pero su disponibilidad futura no está garantizada. No se encontró una especificación oficial estable de longitud máxima; la app utiliza un **límite conservador configurable de 400 residuos**, no una afirmación sobre capacidad garantizada. No trunca automáticamente, no divide proteínas para ensamblarlas ni inventa modelos cuando el servidor falla.

Para un dominio se envía exactamente la subsecuencia solicitada. La respuesta debe coincidir en secuencia y número de residuos, contener una cadena y coordenadas válidas. El PDB de trabajo se renumera a posiciones originales; el JSON guarda el mapeo, hashes de secuencia completa/subsecuencia y la distinción de dominio aislado. No se vuelve a recortar. El hash del PDB devuelto por el servicio se registra aparte del PDB renumerado.

Predecir un dominio aislado **no equivale** a recortarlo de una predicción de proteína completa. Esos métodos se registran y deben considerarse al comparar resultados. No se añadió análisis automático de contactos en PyMOL.

El pLDDT se calcula usando un Cα por residuo, sólo para fuentes conocidas AlphaFold/ESMFold. Se reporta el promedio y el porcentaje menor a 50; los PDB locales/experimentales muestran `NA`. El endpoint ESMFold probado devuelve B-factors en escala histórica 0–1: si todos los valores están en ese rango, las métricas se multiplican por 100 y se registra `confidence_input_scale`. Esa escala se infiere por procedencia y rango de valores; los B-factors originales del archivo se conservan. Las advertencias siguen siendo advertencias: no bloquean docking ni constituyen validación experimental.

## Reportes y reproducibilidad

`structure_report.csv` tiene una fila por proteína: entrada, accession, tipo, fuente, pLDDT, porcentaje bajo, rango, hash, ruta, estado, detalle y uso de caché. Estados: `OK`, `FALLBACK_OK`, `NEEDS_MANUAL`, `RETRY_PENDING`, `INPUT_ERROR`, `FAILED` o `PENDING`. `needs_manual_modeling.txt` lista los problemas con sus estados; una fila `RETRY_PENDING` pide reintentar la consulta, no necesariamente hacer un modelo manual. Ambos se actualizan durante el lote. La consola muestra el resumen final.

`pipeline_config.json` conserva versión de app, fechas UTC, opciones, procedencia y SHA-256 de modelos de entrada y preparados. Los PDB del lote son copias independientes de la caché. Los hashes/jobnames/tokens históricos no cambian. Para lotes antiguos sin metadatos nuevos, la fuente puede aparecer como `Desconocida`; no se inventa confianza retroactiva.

## CLI

Abrir la GUI sin fallback:

```powershell
.venv\Scripts\python app.py --no-fallback
```

Preparar estructuras desde consola, sin ejecutar ni enviar docking:

```powershell
.venv\Scripts\python app.py --prepare-csv entrada.csv --output lote_nuevo --taxon 9606 --allow-fallback
```

`--allow-fallback` es el valor por defecto. `--no-fallback` restringe obtención automática y caché a AlphaFold, conservando PDB propios, resolución de nombres y reportes. La CLI usa el orden predeterminado para lotes nuevos; después puede cambiarse desde la configuración de la GUI. Puede configurarse `--esm-max-length 400`; ampliarlo no garantiza aceptación del servicio. Para reanudar un lote CLI utiliza **Abrir lote guardado** en la GUI.

## Privacidad y límites

ESMFold es un servidor remoto: esta función transmite la secuencia completa o el dominio solicitado. Desactívala para secuencias que no deban compartirse; utiliza un archivo local obtenido con una instalación de modelado configurada para no transmitir secuencias. Un cuaderno en la nube no equivale a modelado local. Esta actualización no instala ColabFold ni ESMFold local, y la preparación alternativa no envía trabajos HDOCK.

Los fallos no se disimulan con un PDB ficticio. Conseguir una estructura no garantiza calidad para docking, interfaces correctas, glicanos, estado oligomérico o regiones biológicamente adecuadas. Revisa los modelos y usa controles experimentales apropiados.

Fuentes: https://github.com/facebookresearch/esm/blob/main/README.md, https://github.com/facebookresearch/esm/blob/main/esm/esmfold/v1/esmfold.py, https://www.uniprot.org/help/accession_numbers, https://www.ncbi.nlm.nih.gov/books/NBK25497/.
