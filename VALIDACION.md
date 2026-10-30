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
