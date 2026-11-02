# Prueba de docking con negativo experimental contextual

[English](protocolo_PD1_PDL1_CD80.en.md) | **Español** · [Guía principal](README.es.md)

## Pregunta

¿El flujo registra correctamente los pares y qué poses/scores produce HDOCK para una interacción positiva y una combinación sin unión detectable reportada en un ensayo publicado?

## Evidencia experimental

Freeman et al. (2000), *Engagement of the PD-1 Immunoinhibitory Receptor by a Novel B7 Family Member Leads to Negative Regulation of Lymphocyte Activation*, J. Exp. Med. 192:1027–1034.

https://pmc.ncbi.nlm.nih.gov/articles/PMC2193311/

El estudio detecta interacción entre las formas humanas de PD-1 y PD-L1 mediante citometría y SPR/BIAcore con proteínas de fusión Ig. Reporta que B7-1/CD80 y B7-2/CD86 humanos solubles no se unieron a PD-1 humano inmovilizado. Los datos de estos negativos se describen en el texto pero no se muestran. No se afirma ausencia absoluta de interacción en cualquier condición, ni un límite numérico de afinidad no publicado.

## Panel humano

| Papel computacional | Proteína | UniProt | Región extracelular |
| --- | --- | --- | --- |
| Ligando común | PD-1 | Q15116 | 25–170 |
| Receptor positivo, A | PD-L1 | Q9NZQ7 | 19–238 |
| Receptor negativo contextual, control | CD80/B7-1 | P33681 | 35–242 |

Fuentes de las regiones: anotación Topological domain / Extracellular de las entradas canónicas de UniProt, consultadas el 1 de noviembre de 2026:

- https://www.uniprot.org/uniprotkb/Q15116/entry
- https://www.uniprot.org/uniprotkb/Q9NZQ7/entry
- https://www.uniprot.org/uniprotkb/P33681/entry

Son dominios extracelulares de modelos canónicos de AlphaFold, no una réplica exacta de los constructos experimentales con Fc. Se excluyen señal, segmento transmembrana y cola citoplasmática. Se conserva la misma región de PD-1 para ambos pares. No se modelan glicanos ni las fusiones Ig del ensayo. Los candidatos tienen distinto tamaño y composición; sus scores no son medidas directas de afinidad.

## Procedimiento en la aplicación

1. Reiniciar la aplicación actualizada y cargar `prueba_PD1_PDL1_CD80.csv`.
2. Dejar albúmina y ubiquitina desmarcadas. Organismo: 9606. Email opcional. No asignar PDB locales.
3. Crear un lote nuevo. Verificar tres estructuras, dos pares preparados y cero errores. El CSV permite la descarga automática y el recorte; no hay que editar PDB a mano.
4. Revisar `pipeline_config.json`: modelos, rangos, fuentes y SHA-256. Conservar este lote separado del ensayo barnasa/barstar.
5. Enviar los dos pares una vez con el mismo motor, intervalo y parámetros. No reutilizar tokens de otros lotes.
6. Consultar hasta disponer de scores y exportar la tabla completa.
7. Pulsar «Consultar HDOCK y descargar modelos» o activar el seguimiento en segundo plano. La aplicación descarga los modelos disponibles y permite abrirlos en ChimeraX o PyMOL. Comprobar composición, cobertura y región de PD-1 presentes en cada uno.
8. Para el positivo, comparar la interfaz con una estructura experimental humana, por ejemplo 4ZQK (contiene un constructo mutado de PD-1, por lo que requiere correspondencia de secuencia): https://www.rcsb.org/structure/4ZQK.

## Interpretación predefinida

No se establece un delta de score numérico esperado ni un punto de corte. Como hipótesis exploratoria, el positivo podría obtener un score más negativo; no se garantiza que HDOCK discrimine los pares. Si el negativo obtiene una puntuación favorable, se revisarán la pose, los dominios, el uso de plantillas, la cobertura, los glicanos omitidos y el alcance del método. No se redefinirá al negativo como positivo sólo por el docking.

El control indica no unión detectable en el ensayo citado. Esta prueba no determina sensibilidad/especificidad del programa con sólo dos pares ni valida un predictor de interacciones de forma general.
