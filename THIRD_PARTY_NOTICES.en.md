# External tools, data and services

**English** | [Español](THIRD_PARTY_NOTICES.md)

The custom Docking Matrix license applies only to original project components. It does not change dependency terms or grant rights over third-party code, executables, models, structures or data.

| Component | Relationship to the app | Official conditions |
| --- | --- | --- |
| HDOCKlite | Optional engine installed by the user; its executables are not distributed in this repository or the project ZIP | [Official license](https://github.com/huang-laboratory/HDOCKlite/blob/main/LICENSE.txt): academic/noncommercial use and redistribution restrictions; contact its authors for commercial use. |
| hdock_batch | Optional external script cloned by the user; invoked through subprocess and not included in the distribution | [Repository](https://github.com/SidSin0809/hdock_batch). Review its conditions and those of the HDOCK server. |
| pandas, requests, openpyxl, Gemmi and Windows-Toasts | Dependencies installed separately through requirements.txt | Retain their licenses and notices when redistributing packages or executables that include them. [pandas](https://github.com/pandas-dev/pandas), [requests](https://github.com/psf/requests), [openpyxl](https://openpyxl.readthedocs.io/), [Gemmi](https://github.com/project-gemmi/gemmi), [Windows-Toasts](https://github.com/DatGuy1/Windows-Toasts). |
| Python / Tkinter | Runtime and interface | [Python licenses](https://docs.python.org/3/license.html). |
| AlphaFold DB, UniProt, NCBI, PDB/PDBe, SWISS-MODEL and ESMFold | Remote data/structure sources and alternative prediction | Their terms, data licenses, limits and citation requirements apply. Provenance is recorded for each structure. |
| PyMOL and ChimeraX | External viewers selected by the user | Not distributed or relicensed by this project. |

Batches, downloaded structures, models, personal settings and results are not part of the distributed code. Business permission from Andrés Ahumada covers only rights he can grant over Docking Matrix; external providers may require additional permissions.

Publications must cite this software according to `CITATION.cff` and acknowledge the tools and sources used according to their own instructions.
