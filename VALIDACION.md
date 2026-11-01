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
