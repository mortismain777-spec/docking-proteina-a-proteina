# Cálculo local con HDOCKlite

[English](INSTALACION_LOCAL.en.md) | **Español** · [Guía principal](README.es.md)

El modo local ejecuta HDOCKlite global ab initio. No requiere una grid box manual: explora posiciones y orientaciones de ambos participantes. Las dimensiones registradas en el informe describen las estructuras; no son una caja de búsqueda ni una optimización del bolsillo. El servidor web puede utilizar plantillas, por lo que los modos no deben mezclarse como si fueran el mismo protocolo.

## Windows: instalar WSL una vez

1. Guarda el trabajo y abre PowerShell **como administrador** desde el menú Inicio.
2. Ejecuta `wsl --install` siguiendo la guía oficial: https://learn.microsoft.com/windows/wsl/install.
3. Reinicia sólo cuando Windows lo solicite. La aplicación no reinicia el equipo por su cuenta.
4. Abre Ubuntu y completa su primer inicio (usuario y contraseña). No compartas la contraseña en el chat.
5. Comprueba en PowerShell `wsl --list --verbose` y `wsl --exec uname -m`. HDOCKlite distribuido aquí requiere Linux x86-64.

La descarga de binarios no sustituye WSL. Si el sistema necesita elevar permisos, activar virtualización o reiniciar, la aplicación muestra el requisito en lugar de simular un cálculo local.

## Instalar o preparar el motor

Lee primero las condiciones oficiales: https://github.com/huang-laboratory/HDOCKlite/blob/main/LICENSE.txt. Permiten uso académico/no comercial y restringen la redistribución fuera del grupo o laboratorio; un uso comercial requiere consultar a los autores.

Desde la carpeta del proyecto, tras revisar que tu uso está autorizado:

```powershell
.venv\Scripts\python setup_local.py --download --license-reviewed
```

Si los archivos ya están en `tools/hdocklite`, basta preparar sus permisos y comprobarlos:

```powershell
.venv\Scripts\python setup_local.py
```

Para otra distribución: añade `--distribution Ubuntu` (sustituye el nombre si corresponde). El programa convierte las rutas con wslpath y utiliza listas de argumentos, sin construir órdenes de shell con nombres de proteínas.

En Linux nativo se ejecuta `python3 setup_local.py --download --license-reviewed`. No se requiere WSL. Se deben instalar las bibliotecas que indique el cargador de Linux si falta alguna dependencia del binario oficial.

## Usar el modo local

1. Introduce nombres, genes o accessions y el TaxID apropiado. Los nombres ambiguos se detienen; utiliza entonces UniProt ID.
2. Prepara un lote nuevo. Selecciona estructura completa o región extracelular si está anotada inequívocamente; también puedes proporcionar rangos y cadenas en el CSV.
3. Revisa los informes de preparación y las advertencias. La limpieza automática no reconstruye residuos, añade glicanos, determina complejos biológicos ni valida la hipótesis experimental.
4. Selecciona **Este equipo · HDOCKlite** en la pestaña 2, indica la carpeta `tools/hdocklite` y pulsa **Comprobar motor local**.
5. Tras revisar la licencia, marca la casilla correspondiente y pulsa **Calcular pares en este equipo**.
6. Los modelos y tablas quedan bajo `local/` y `resumen_local.*`. No hay tokens HDOCK porque los PDB no se envían al servidor durante el cálculo local.

La descarga inicial de estructuras y software sí requiere Internet. Con los PDB y motor ya instalados, el cálculo local no utiliza el servidor. Se ejecuta un par a la vez para limitar consumo en equipos modestos. No se promete un tiempo sin medirlo con tu hardware y estructuras.

**Pausar tras el par activo** deja terminar el cálculo actual y conserva su resultado antes de detener el siguiente. Mantén la ventana abierta durante el cálculo local. Los resultados locales y del servidor se guardan por separado y no se fusionan en un mismo ranking.
