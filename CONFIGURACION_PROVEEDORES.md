# Configurar fuentes gratuitas de estructuras — 0.4.0

[English](CONFIGURACION_PROVEEDORES.en.md) | **Español** · [Guía principal](README.es.md)

## Primer uso

1. Cierra y vuelve a abrir Docking Matrix desde el acceso directo del escritorio.
2. Pulsa **⚙ Configuración**, arriba a la derecha, fuera de las pestañas del pipeline.
3. Selecciona una fuente y usa **↑ Subir** o **↓ Bajar**. **Activar / desactivar** permite excluirla. Debe quedar al menos una fuente activa.
4. Guarda la configuración. Las preferencias persisten al cerrar y abrir la app, y se copian a cada lote nuevo.
5. Deja marcada **Permitir fuentes alternativas según Configuración** en la pestaña de proteínas.

El orden inicial es **AlphaFold DB → PDB / PDBe → SWISS-MODEL Repository → ESMFold**. Puedes colocar ESMFold antes de PDB/SWISS-MODEL si prefieres predecir antes de buscar estructuras existentes. Un PDB propio tiene prioridad. Si la casilla general de alternativas está desmarcada, se utiliza sólo AlphaFold, aunque configures otro orden.

## Caché y errores temporales

**Usar caché validada antes de consultar las fuentes** evita repetir descargas/predicciones. Sólo considera fuentes activas y, dentro de la caché, respeta su orden. Una copia de una fuente inferior puede evitar consultas remotas a una superior: la prioridad de caché es explícita. Para exigir una consulta nueva con tu orden, desmarca esa opción y crea un lote nuevo; la caché no se borra.

**Probar la siguiente fuente tras agotar reintentos de errores temporales** permite continuar después de 504, 503, 429 o timeout. El fallo queda como `RETRY_PENDING` en la traza; no se afirma que la proteína no existe. Si se desactiva, se detiene la obtención de esa proteína ante el primer fallo temporal agotado. Se mantienen los reintentos limitados, el backoff y `Retry-After`.

Un lote anterior conserva su política hasta que la cambies explícitamente. Para cambiar sólo intentos pendientes, marca **Aplicar también a estructuras pendientes del lote abierto**, guarda y pulsa **Reintentar preparación que falló**. Esto no reemplaza estructuras preparadas, no cambia hashes ni vuelve a enviar trabajos HDOCK. Para comparar fuentes sobre proteínas ya preparadas, crea otro lote.

## Fuentes incluidas

| Fuente | Tipo | Acceso |
| --- | --- | --- |
| AlphaFold DB | Modelo precomputado | Descarga pública; selección canónica y recorte existentes. |
| PDB / PDBe | Estructura experimental existente | API de PDBe/SIFTS y coordenadas RCSB; sin cuenta ni facturación. |
| SWISS-MODEL Repository | Modelo por homología existente | API pública del repositorio; sin token y sin crear trabajos nuevos. |
| ESMFold | Predicción nueva por secuencia | Endpoint público; transmite la secuencia. Límite conservador configurable de 400 residuos. |

No se han añadido servicios con facturación. **El modelado nuevo de SWISS-MODEL Workspace no está incluido**: requiere configurar cuenta/token. No aparece como proveedor funcional. Las accesiones RefSeq siguen disponibles para ESMFold; PDB y SMR automáticos requieren UniProt canónico y no sustituyen silenciosamente isoformas.

## Selección conservadora

PDB consulta las mejores estructuras de PDBe, selecciona una cadena y usa SIFTS para convertir `label_seq_id` a posiciones UniProt. No confunde numeración del autor con numeración de secuencia. Exige identidad exacta y cobertura con Cα de **todos los residuos solicitados**. Rechaza mutaciones, huecos y mapeos ambiguos; no reconstruye residuos. Inspecciona como máximo ocho candidatos por proteína. Conserva coordenadas, selecciona el primer modelo/conformación y registra entrada, cadena, resolución, método y hash del origen. Gemmi lee mmCIF; no se analiza como texto PDB.

SMR se consulta con `provider=swissmodel` y sólo acepta resultados identificados como `SWISSMODEL`, excluyendo espejos AlphaFold y entradas PDB. Prioriza GMQE entre candidatos que cubran la región, inspecciona hasta cinco plantillas distintas y verifica secuencia/numeración de coordenadas. Un modelo del repositorio puede no cubrir la proteína completa.

Una cadena seleccionada automáticamente no determina el estado biológico adecuado. Las copias excluyen otras cadenas, ligandos y cofactores, conforme a la preparación existente. Revisa conformación, dominios, oligomerización y modificaciones. Una estructura experimental del complejo puede introducir información previa de la interfaz al evaluar el docking.

## Procedencia visible

En **Resultados y modelos**, selecciona una fila y pulsa **Ver procedencia del par**. Aparecen por separado fuente, método, entrada/cadena/plantilla/URL, pLDDT y otras métricas del ligando y del receptor. La fuente de la estructura es independiente del motor de docking.

La tabla/exportaciones añaden `Metodo_Ligando`, `Metodo_Receptor`, `Origen_Ligando`, `Origen_Receptor`, `Calidad_Ligando` y `Calidad_Receptor`. `structure_report.csv` incorpora método, entrada, calidad y traza de proveedores. `pipeline_config.json` conserva la política e intentos por proteína.

Los B-factors experimentales **no son pLDDT**. GMQE y `QMEAN.avg_local_score` de SMR tampoco se convierten a pLDDT: se muestran por separado y el pLDDT queda vacío/NA. Para lotes antiguos se recupera procedencia de los metadatos guardados sin reconstruir pares; lo desconocido queda explícito.

## Fuentes oficiales

- https://www.ebi.ac.uk/pdbe/api/doc/sifts.html
- https://www.rcsb.org/docs/general-help/website-faq
- https://swissmodel.expasy.org/docs/repository_help
- https://github.com/facebookresearch/esm
- https://gemmi.readthedocs.io/en/latest/cif.html
