# Estado de la primera versión

Fecha de revisión: 30 de octubre de 2026.

Comprobaciones realizadas con Python 3.12 en Windows:

- 12 pruebas automatizadas correctas (`python -W error::ResourceWarning -m unittest -v`). Incluyen generación de matriz y controles, fallos parciales, resolución ambigua, descarga simulada, scores, exportación, subproceso real de prueba, reanudación y conciliación de tokens.
- Compilación de los módulos y análisis de sintaxis compatible con Python 3.9. No se ejecutó la suite en un intérprete 3.9.
- Tkinter abre la aplicación y construye sus tres pestañas sin excepciones. La captura de pantalla nativa falló en el entorno de prueba, por lo que queda pendiente la revisión visual manual.
- Consulta real a UniProt: `EGFR`, TaxID 9606, entrada curada `P00533`.
- Descarga real desde AlphaFold: `P69905`; PDB validado y SHA-256 calculado. Para esta prueba se incorporaron las CA confiables de Windows a un bundle temporal manteniendo verificación TLS.

Límites pendientes de comprobar:

- No se enviaron trabajos reales a HDOCK ni se instaló el motor externo en el entorno de prueba. El adaptador de CLI se ejercitó con un motor simulado.
- El parseo de scores se probó con HTML sintético representativo, no con una página de resultados real capturada de HDOCK. Ante un formato distinto se conserva la URL y el score vacío.
- No se realizó validación científica del protocolo ni de los controles. La albúmina y la ubiquitina son referencias provisionales.

Antes de un lote grande, instalar el motor según el README y comprobar un único par y su score manualmente en HDOCK. Mantener los datos del lote fuera del control de versiones.

## Actualización del 1 de noviembre de 2026

- Se instaló el motor externo, Playwright y Chromium; el usuario envió correctamente dos trabajos a HDOCK y recibió sus tokens.
- Se corrigió la lectura de scores presentados en filas y se verificó con las páginas reales de los dos trabajos.
- Se sustituyó la etiqueta RBP por Ligando en la interfaz, ejemplos y exportaciones. CSV y lotes anteriores siguen siendo compatibles y conservan sus identificadores, estructuras, tokens y scores.
- 15 pruebas automatizadas correctas. Se abrió el lote anterior en la aplicación y se comprobó la columna Ligando con sus dos scores conservados, sin modificar ese lote ni enviar nuevos trabajos.
- El navegador puede instalarse dentro del proyecto; el adaptador utiliza esa ruta cuando existe para evitar depender de la caché de otro contexto de ejecución.

Esta actualización valida el funcionamiento del flujo, no la interpretación científica de los scores ni la idoneidad de los controles.

## Panel experimental PD-1 / PD-L1 / CD80

Se añadió selección opcional de albúmina y ubiquitina para los lotes nuevos, recorte mediante columnas opcionales `residuo_inicio,residuo_fin` y selección del modelo canónico exacto cuando AlphaFold devuelve isoformas adicionales.

Se verificó con descargas reales el panel humano Q15116 (25–170), Q9NZQ7 (19–238) y P33681 (35–242): tres estructuras preparadas, dos pares, cero errores, sin PDB locales y sin enviar nuevos trabajos. El CSV y el protocolo de este panel documentan el negativo reportado por Freeman et al. (2000), los constructos y los límites de extrapolación a modelos sin glicanos ni fusiones Ig.

Las nuevas pruebas cubren selección de isoforma, recorte, cobertura de residuos, validación de límites, exclusión de referencias y protección de un lote cuando cambia su rango. El panel está preparado para una prueba exploratoria; todavía no se ha ejecutado docking para él.

## Modo local, descarga y notificaciones

- 30 pruebas automatizadas correctas, incluidas preparación de átomos pesados y geometría, extracción de modelos, conservación de coordenadas, aislamiento de los motores, reanudación y avisos sin duplicados ni avisos durante la espera.
- Descarga real de cinco modelos para cada uno de dos trabajos HDOCK terminados (10 originales y 10 copias para visor), sin reenviar trabajos ni modificar el lote original. Se verificó apertura estructural en ChimeraX 1.12 mediante su interfaz de línea de comandos.
- El seguimiento se lanzó como proceso separado; leyó los trabajos, guardó resultados/tablas y finalizó al tener los modelos disponibles. Se probó la exclusión de monitores duplicados y persistencia de avisos por token.
- Windows-Toasts instalado en el entorno virtual. La API de Windows aceptó un aviso de prueba; la visualización final depende de las preferencias de Windows y no se fuerza habilitando notificaciones del sistema.
- Se revisó visualmente la pestaña de ejecución mediante captura nativa. La aplicación abre modos local/servidor, conserva los scores del lote histórico y muestra las nuevas etiquetas.
- La preparación del panel PD-1/PD-L1/CD80 se verificó con estructuras reales: 146/220/208 residuos, tres copias de trabajo, dos pares y cero errores. Se registraron estadísticas pLDDT y dimensiones.
- El adaptador local ejecutó subprocesos simulados de hdock/createpl, produjo PDB y reanudó sin mezclar tokens del servidor. Los ejecutables oficiales HDOCKlite se descargaron fuera del código distribuido. **No se ha verificado todavía un cálculo HDOCKlite real en este equipo**: requiere completar WSL/Ubuntu y su primer inicio, con elevación/reinicio si Windows lo solicita.

La preparación automatiza limpieza, selección inequívoca y trazabilidad. No garantiza dominios biológicamente adecuados, reconstrucción de regiones ausentes, glicanos, protonación específica, minimización ni validación experimental. HDOCKlite usa búsqueda global; no se presenta una grid box ficticia ni se equipara su protocolo al híbrido del servidor.
