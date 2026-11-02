# Herramientas, datos y servicios externos

La licencia personalizada de Docking Matrix se aplica únicamente a los componentes originales del proyecto. No cambia las condiciones de sus dependencias ni concede derechos sobre código, ejecutables, modelos, estructuras o datos de terceros.

| Componente | Relación con la app | Condiciones oficiales |
| --- | --- | --- |
| HDOCKlite | Motor opcional instalado por el usuario; no se distribuyen sus ejecutables en este repositorio ni en el ZIP del proyecto | [Licencia oficial](https://github.com/huang-laboratory/HDOCKlite/blob/main/LICENSE.txt): uso académico/no comercial y restricciones de redistribución; consultar a sus autores para uso comercial. |
| hdock_batch | Script externo opcional clonado por el usuario; se invoca por subprocess y no se incluye en la distribución | [Repositorio](https://github.com/SidSin0809/hdock_batch). Revisar sus condiciones y las del servidor HDOCK. |
| pandas, requests, openpyxl, Gemmi y Windows-Toasts | Dependencias instaladas por separado mediante requirements.txt | Conservar sus licencias y avisos si se redistribuyen paquetes o ejecutables que las incluyan. [pandas](https://github.com/pandas-dev/pandas), [requests](https://github.com/psf/requests), [openpyxl](https://openpyxl.readthedocs.io/), [Gemmi](https://github.com/project-gemmi/gemmi), [Windows-Toasts](https://github.com/DatGuy1/Windows-Toasts). |
| Python / Tkinter | Entorno de ejecución e interfaz | [Licencias de Python](https://docs.python.org/3/license.html). |
| AlphaFold DB, UniProt, NCBI, PDB/PDBe, SWISS-MODEL y ESMFold | Fuentes remotas de datos o estructuras y predicción alternativa | Se aplican sus términos, licencias de datos, límites y requisitos de citación. La procedencia se registra por estructura. |
| PyMOL y ChimeraX | Visores externos seleccionados por el usuario | No se distribuyen ni relicencian en este proyecto. |

Los lotes, estructuras descargadas, modelos, configuraciones personales y resultados no forman parte del código distribuido. Una autorización empresarial de Andrés Ahumada cubre sólo los derechos que pueda conceder sobre Docking Matrix; puede ser necesario obtener permisos adicionales de los proveedores externos.

Las publicaciones deben citar este software según CITATION.cff y reconocer también las herramientas y fuentes utilizadas conforme a sus propias instrucciones.
