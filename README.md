# Docking Matrix: protein–protein docking

**English** | [Español](README.es.md)

**Author:** Andrés Ahumada · [GitHub: mortismain777-spec](https://github.com/mortismain777-spec) · **Contact:** [mortismain777@gmail.com](mailto:mortismain777@gmail.com)

A Python 3.9+ / Tkinter desktop application for preparing a protein ligand × receptor matrix, submitting pairs to HDOCK through the external `hdock_batch` script, and exporting results to CSV/Excel. Both participants are proteins.

**Documentation is available in English and Spanish. The application interface and code comments are currently in Spanish.** This guide keeps the actual Spanish button labels and CSV fields alongside English explanations so you can find them in the app. No separate application download is needed for either documentation language.

## License, citation and collaboration

Personal, educational and noncommercial research use is free under the [academic/noncommercial attribution license](LICENSE) ([English translation](LICENSE.en.md)). Retain the author credit and license when sharing copies or modifications, identify your changes, and cite the software when publishing results obtained with it. See [CITATION.cff](CITATION.cff); citing the software does not imply coauthorship of a publication.

> Ahumada, A. (2026). *Docking Matrix: pipeline de docking proteína-proteína* (version 0.4.0) [Software]. https://github.com/mortismain777-spec/docking-proteina-a-proteina

**Business collaboration:** I welcome conversations with companies, laboratories and research teams interested in using, adapting or extending the app. Scientific collaboration, joint development and terms tailored to a project can be discussed. Any business use, including internal research, requires prior written permission. Contact **mortismain777@gmail.com**. A conversation does not necessarily imply payment or automatically grant permission.

**Suggestions and comments:** open an [Issue](https://github.com/mortismain777-spec/docking-proteina-a-proteina/issues) in English or Spanish whenever you find a problem, something confusing or an idea worth considering. Code contributions and scientific collaborations are welcome; see [the contribution guide](CONTRIBUTING.en.md).

This project is source-available with commercial-use restrictions, rather than OSI-approved open-source software. External engines, tools and data retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.en.md). The Spanish `LICENSE` is authoritative; its English translation is provided for convenience.

## Documentation

| Topic | English | Español |
| --- | --- | --- |
| Installation and workflow | This page | [README.es.md](README.es.md) |
| Local HDOCKlite engine | [Local setup](INSTALACION_LOCAL.en.md) | [Instalación local](INSTALACION_LOCAL.md) |
| Structure provider settings | [Provider settings](CONFIGURACION_PROVEEDORES.en.md) | [Configuración](CONFIGURACION_PROVEEDORES.md) |
| Alternative structures, cache and CLI | [Structure acquisition](ESTRUCTURAS_ALTERNATIVAS.en.md) | [Estructuras alternativas](ESTRUCTURAS_ALTERNATIVAS.md) |
| Checks and known limitations | [Validation record](VALIDACION.en.md) | [Validación](VALIDACION.md) |
| Contextual experimental control example | [PD-1 / PD-L1 / CD80](protocolo_PD1_PDL1_CD80.en.md) | [Protocolo](protocolo_PD1_PDL1_CD80.md) |
| Contributions | [Contribution guide](CONTRIBUTING.en.md) | [Contribuciones](CONTRIBUTING.md) |
| License | [Translation](LICENSE.en.md) | [Authoritative license](LICENSE) |
| External components | [Notices](THIRD_PARTY_NOTICES.en.md) | [Avisos](THIRD_PARTY_NOTICES.md) |

The current version also supports **local HDOCKlite computation on Linux/WSL**, traceable structure preparation, model downloads, PyMOL/ChimeraX viewing, background monitoring and desktop notifications. Local and server results remain separate. Version 0.4.0 adds **⚙ Configuración** to order and enable free structure sources: AlphaFold DB, PDB/PDBe, SWISS-MODEL Repository and ESMFold. Existing batches retain their structures and tokens.

## 1. Install the application

Install Python 3.9 or later with Tkinter from https://www.python.org/downloads/. On Windows, check `py -3 --version`; some computers have an old MGLTools `python` on PATH. Linux may require the `python3-tk` package.

```powershell
git clone https://github.com/mortismain777-spec/docking-proteina-a-proteina.git
cd docking-proteina-a-proteina
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

On macOS/Linux, replace `py -3` with `python3` and `.venv\Scripts\python` with `.venv/bin/python`. The local HDOCKlite engine requires Linux x86-64, including through WSL on Windows.

## 2. Install the external submission engine

Clone **hdock_batch**, with an underscore. The upstream documentation referred to a hyphenated name and a `requirements.txt` absent from the inspected tree; these commands use the actual repository and dependencies:

```powershell
git clone https://github.com/SidSin0809/hdock_batch.git
.venv\Scripts\python -m pip install pandas playwright
.venv\Scripts\python -m playwright install chromium
```

If Chromium cannot be found in the user cache, install it inside the project:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.playwright-browsers"
.venv\Scripts\python -m playwright install --only-shell chromium
```

When `.playwright-browsers` exists, the adapter explicitly sets that path for the engine. This directory is excluded from Git. After changing the adapter, restart the application and reopen the saved batch to preserve previous work.

Keep the external script separate. The app invokes it through `subprocess` with separate arguments and without `shell=True`:

```text
python hdock_batch.py jobs.csv --out output_directory -j 1
```

You can select a different Python executable on the execution tab; its environment must contain pandas, Playwright and Chromium. One simultaneous submission and a configurable delay limit load and isolate failures. The external script handles the form and token capture; this application does not implement direct HTTP submission.

For computation on your own computer instead, follow [local setup](INSTALACION_LOCAL.en.md).

## 3. Prepare input

Load `ejemplo_entrada.csv`, edit CSV text in the app or paste one identifier per line using **Añadir listas pegadas** / **Pegar listas de proteínas**.

**Keep these CSV headers and accepted values in Spanish, even when following the English documentation.** Translating them to `type`, `identifier` or `ligand` is not supported.

```csv
tipo,identificador,nombre_comun,categoria
ligando,P09651,HNRNPA1,
ligando,P22626,HNRNPA2B1,
receptor,P00533,EGFR,A
receptor,P04626,ERBB2,B
receptor,P08581,MET,C
```

- `tipo`: `ligando` (protein ligand) or `receptor`. Legacy `RBP` is accepted as `ligando`, case-insensitively.
- `identificador`: UniProt accession, exact gene symbol or protein name. Names are resolved through UniProt REST using the selected organism TaxID (9606 for human by default), prioritizing reviewed entries. Ambiguous names require an accession rather than an arbitrary choice. Recognized protein RefSeq accessions are supported through alternative sequence acquisition.
- `nombre_comun`: a readable display name.
- `categoria`: A/B/C for candidate receptors, `control` for custom controls; leave it empty for ligands. Control rows remain distinct.
- Optional `pdb_local`: a local PDB override; relative paths in a loaded CSV resolve against the CSV's folder. Use absolute paths when pasting CSV text.
- Optional `residuo_inicio,residuo_fin`: positive inclusive residue bounds, both provided. A requested interval must be fully covered in one chain without insertions. For ESMFold, the requested subsequence is predicted and renumbered to original positions. Predicting a domain alone is different from cropping a full-protein prediction.
- Optional `cadenas`: selected chains, for example `A` or `"A,B"`.

Exact duplicates are removed by type/identifier; conflicting metadata are rejected. Unify aliases that resolve to the same accession before preparing a batch. Examples illustrate the format and do not assert experimentally validated interactions.

The AlphaFold API `https://alphafold.ebi.ac.uk/api/prediction/{accession}` supplies `pdbUrl`. The exact requested accession is selected, excluding other isoforms; ambiguous fragments require an explicit local PDB choice. **Asignar PDB local** / **Asignar PDB propio** overrides retrieval. After resolving a missing structure, use the preparation retry/review button.

Preparation retains originals in `structures/` and writes heavy-atom copies to `prepared/`: it removes water/HETATM and hydrogens, selects an alternate conformer by occupancy and supports chain selection. Geometry, SHA-256, incomplete-backbone warnings and applicable confidence metrics are recorded. It does not rebuild residues, add glycans, minimize or perform specific protonation.

**Región extracelular anotada en UniProt** automatically selects an extracellular interval only when the annotation is unambiguous and no range was already supplied. A different range or already-used model requires a new batch. The local engine performs global ab initio docking without a manual grid box; reported geometric dimensions describe the structure and do not restrict the search.

## 4. Run a batch

```powershell
.venv\Scripts\python app.py
```

On Windows, `ejecutar.bat` also launches the app after dependencies are installed. If an institutional network causes `CERTIFICATE_VERIFY_FAILED`, configure `REQUESTS_CA_BUNDLE` with an approved institutional PEM CA bundle; keep TLS verification enabled.

1. Load proteins, choose the organism and assign any local PDB overrides.
2. Click **Preparar proteínas y crear pares** (prepare proteins and create pairs), then choose a folder. A dated subfolder is created. Preparation does not calculate docking or submit to HDOCK.
3. Review the log, pair count and `pares_omitidos.csv`. A structure failure omits only pairs involving that structure.
4. In **Ejecución y seguimiento** (execution and monitoring), select **Servidor HDOCK** and check `hdock_batch.py` and its Python, or select **Este equipo · HDOCKlite** after installing the local engine.
5. For the server, click **Enviar pares a HDOCK** (submit pairs). The confirmation states how many will be attempted; accepted submissions are skipped. Locally, click **Calcular pares en este equipo** (calculate on this computer).
6. Logs show messages, errors and tokens. **Enviado** means a token exists, not that computation has finished. The progress bar counts pairs with an available score. Counters distinguish proteins, prepared pairs, submitted pairs and ready results.
7. Automatic monitoring is enabled by default: every 5 minutes, download up to 5 models per pair and request a Windows notification when a score appears. You can adjust the interval (1–60 minutes) and model count (1–20). **Consultar HDOCK y descargar modelos** checks immediately without resubmission.
8. In **Resultados y modelos** (results and models), filter A/B/C/control, open a folder/model and export the view. **Etapa del par** is the progress stage; **Detalle de error** explains a failure; **Última consulta** is a timestamp. **Ver procedencia del par** shows ligand and receptor provenance separately.

## Background monitoring and model files

The monitor is a separate local process. It starts after submission when the automatic option is enabled; for an already-submitted batch use **Activar seguimiento en segundo plano**. It can continue with the GUI closed while Windows remains on, connected and awake. It is not installed as a startup service/task. After a reboot, reopen the batch and reactivate monitoring. It stops after collecting accepted pairs' models, when paused, or after 48 hours.

Notifications are requested once per result/token, with no waiting notifications. Visibility depends on Windows notification/Do Not Disturb settings. Use **Probar notificación** to test. API failures are logged; requesting a notification does not prove it appeared on screen.

Official `model_1.pdb` and subsequent links are downloaded; homology model 0 is excluded from the docking selection. Original files and `_visor.pdb` viewer copies with distinct chain IDs are preserved without coordinate movement, together with SHA-256 and provenance. Model folders include `abrir_chimerax.cxc` and `abrir_pymol.pml` sessions; open them from that folder. **Abrir mejor modelo en visor** opens model 1 in the selected viewer. Download failures do not erase an available score.

The monitor writes `monitor_state.json`, `monitor.log` and `resumen_hdock_auto.*`. The GUI imports its results without the monitor overwriting GUI configuration. A file lock prevents duplicate monitors for a batch. **Pausar seguimiento** stops polling and does not cancel server jobs.

## 5. Controls and interpretation

In new GUI batches, bovine albumin **P02769** and ubiquitin **PDB 1UBQ** are optional references, unchecked by default. Add experiment-specific controls as receptor rows with category `control`. Older batches retain their original participants. All pairs use the same selected engine and submission settings.

The label `control` does not experimentally certify a protein. Record the supporting publication, species, constructs and conditions, including relevant modifications, glycans, fusion tags and presentation. **There is no universally negative protein.** Albumin and ubiquitin can bind some protein ligands; justify their use for the particular hypothesis. Structure size, domains, quality and surface composition can affect comparisons.

HDOCK scores rank an exploratory screen. They are not experimental free energies, direct affinity measurements or proof of interaction. A known positive control and experimental validation improve interpretation. See the [contextual control example](protocolo_PD1_PDL1_CD80.en.md).

## 6. Batch files and resuming

| File | Contents |
| --- | --- |
| `pipeline_config.json` | Input, TaxID, controls, UTC dates, paths, sources, PDB/engine SHA-256, pairs, errors and scores |
| `structures/` | Independent copies of input PDB files |
| `prepared/` | Working structures and preparation reports |
| `jobs.csv` | `receptor_pdb,ligand_pdb,jobname,email` for the prepared batch |
| `pares_omitidos.csv` | Omitted pairs and reasons |
| `run-log.csv` | Accumulated docking submission log compatible with the external engine |
| `attempts/` | CSV, console output and log for each individual attempt |
| `reports/` | Retrieved HTML as score evidence |
| `models/` | Original HDOCK models, viewer copies, sessions and provenance |
| `local/` | Local HDOCKlite runs, commands, structures, logs and models |
| `monitor_state.json` | Independent monitoring results and notification state |
| `resumen.csv` / `resumen.xlsx` | Sorted summary; highlighted controls and Excel filter |

Exports retain existing fields and add `Motor, Modelos_Descargados, Carpeta_Modelos, Error_Descarga, Ultima_Consulta`, plus per-protein provenance. The minimum numeric value explicitly labelled **Docking Score** on the page is selected; otherwise it remains empty. RMSD/confidence is not treated as a docking score. Local results use `resumen_local.*` without server tokens/URLs.

Legacy `RBP` batches open without losing structures, tokens or scores. New views/exports show `Ligando`; internal historical keys and `jobname` values remain stable to prevent duplicate submissions. Old exports are not rewritten; export again for the updated header. The parser supports real HDOCK tables with `Docking Score` as a row. After an app update, restart, open the saved batch and query results rather than resubmit.

Use **Abrir lote guardado** and select the folder containing its configuration and `run-log.csv`. Accepted submissions are skipped even without scores. Failures are not automatically resubmitted: inspect logs and enable the retry checkbox. Historical structures and job names remain unchanged; use a new batch for new preparation settings.

If interrupted during submission, `submission-in-flight.json` preserves the attempt. On reopening, a token is recovered from that attempt's log if available; otherwise new submissions remain blocked pending reconciliation. Inspect `attempts/.../console.log` and HDOCK; add a recovered entry to `run-log.csv`, or archive the marker only after verifying no submission occurred. An absent token is not proof that the server received nothing; exactly-once delivery cannot be guaranteed during network failures without server idempotency support.

**Pausar tras el par activo** finishes the active subprocess before stopping the next pair, preserving its token or local result. It does not cancel HDOCK jobs. Do not change structures or delete batch logs; a different hash requires a new batch. Paths are absolute, so keep the batch folder in its original location.

Batches, execution emails, structures, personal settings and results are excluded from Git by default. Published code and commit history are public; the author's contact email intentionally published here is mortismain777@gmail.com. Review staged files before contributing.

## 7. Development and checks

```powershell
.venv\Scripts\python -m unittest -v
```

Tests cover pair/control generation, partial failures, ambiguous resolution, structure handling, score fields, exports and real subprocesses using simulated engines, resuming and provenance. They do not submit real docking jobs or constitute scientific validation. Tkinter updates run only on the main thread; workers communicate through a queue. See the [validation record](VALIDACION.en.md) for historical checks and remaining limitations, including local-engine verification.

Modules include `data_fetcher.py` (resolution/download), `structure_cache.py` (cache/reports), `structure_providers.py` and `provider_settings.py` (providers/policy), `preparation.py` (preparation), `pipeline.py` (matrix/persistence), `job_runner.py` (submission), `local_engine.py` (HDOCKlite/WSL), `results_parser.py` (scores/exports), `model_files.py` (models/viewers), `result_monitor.py` (monitoring), `desktop_notify.py` (notifications) and `app.py` (GUI).

## Sources and integration limits

- External engine, CSV schema and CLI: https://github.com/SidSin0809/hdock_batch
- AlphaFold API: https://alphafold.ebi.ac.uk/api-docs
- UniProt: https://www.uniprot.org/help/api_queries
- 1UBQ: https://www.rcsb.org/structure/1UBQ
- HDOCK: http://hdock.phys.hust.edu.cn/

The adapter depends on the external site and engine. `hdock_batch` currently uses HTTP for the server, without encrypted transport at that endpoint. Its code is not included or modified. This application does not require HDOCK credentials or guarantee additional server authentication. Form changes may require an external engine update. Initial automated tests did not submit real jobs; subsequent real-flow checks are documented separately in the validation record.
