# Alternative structure acquisition — version 0.4.0

**English** | [Español](ESTRUCTURAS_ALTERNATIVAS.md) · [Main guide](README.md)

Source priority, including PDB and SWISS-MODEL Repository, is configurable through **⚙ Configuración**. See [provider settings](CONFIGURACION_PROVEEDORES.en.md). Existing batches retain their options until explicitly changed.

## Using the application

1. Restart the app. Accepted HDOCK jobs continue on the server.
2. Enter names/genes with an organism, or UniProt/RefSeq accessions. Ambiguous names require an accession. RefSeq versions are retained. Automatic extracellular selection requires an unambiguous UniProt annotation; use explicit bounds for RefSeq.
3. Keep **Permitir fuentes alternativas según Configuración** enabled to allow fallback. Disable ESMFold in settings if sequence transmission to that server is not authorized. The general checkbox is enabled by default for new batches.
4. Click **Preparar proteínas y crear pares**. The console shows each protein's source and the preparation progress bar advances. Failures omit only affected pairs.
5. Use **Ver informe de preparación**. The batch folder contains `structure_report.csv`, `needs_manual_modeling.txt` and individual reports in `prepared/`.
6. Results add `Fuente_Ligando`, `Fuente_Receptor`, `pLDDT_Ligando` and `pLDDT_Receptor`, retaining existing columns and controls.

To resume, open the saved batch and use **Reintentar preparación que falló**. Options apply to new attempts without replacing prepared structures. Historical batches open with fallback disabled until explicitly enabled. Use a new batch to change a protein or a model already used.

## Priority and errors

1. Explicit PDB selection through the GUI or CSV `pdb_local`. GUI selection takes precedence when both are supplied.
2. Validated cache, when cache-first is enabled, respecting enabled sources and their configured order. With fallback disabled, only AlphaFold cache is automatically eligible. See the provider settings guide for the complete cache policy.
3. Enabled remote sources in batch order: initially AlphaFold DB, PDB/PDBe, SWISS-MODEL Repository, ESMFold. AlphaFold retains canonical selection, fragment checks and cropping.
4. If a source has no usable model, try the next. Temporary errors allow continuation only if that option is enabled. A PDB download-link 404 is not interpreted as an absent AlphaFold prediction. Ambiguous responses do not trigger arbitrary fragment selection.
5. Recognized protein RefSeq/GenBank accessions are not AlphaFold keys: with fallback enabled, obtain FASTA from NCBI and use ESMFold, without requiring a UniProt equivalent. Inputs without one unique sequence of standard amino acids are rejected.
6. Record an unresolved protein's reason and continue. `RETRY_PENDING` identifies temporary lookup failures; `INPUT_ERROR` identifies HTTP 400 input errors.

AlphaFold and UniProt resolution retain three total GET attempts through the existing adapter. FASTA/ESMFold use **three total attempts**, waiting 2 and 4 seconds for 429/500/502/503/504, connection failures or timeouts. A larger `Retry-After`, in seconds or HTTP-date form, is respected. Input/permanent errors are not retried. Consecutive call starts to the same FASTA/ESMFold service are at least one second apart. Prediction POST read timeout is 300 seconds per attempt. A timed-out POST does not prove the server did not start computing.

**Detener preparación** interrupts waits and prevents starting the next protein. An active synchronous request can remain pending until its timeout; server cancellation is not instantaneous. Completed work remains in configuration/reports. Preparation does not write `run-log.csv`, which remains exclusively the docking submission log.

## Cache and local PDB files

`pdb_cache/` is created automatically beside the project for new batches. JSON sidecars form an offline index. Identity includes resolved/original identifier, organism, SHA-256 of the represented sequence, residue range, chains and source. Filenames use the SHA-256 of that identity, not a user identifier as a path. Metadata include PDB hashes. Coordinates, Cα residues, single-model status, sequence/hash and parameters are validated before reuse; corrupt entries are ignored.

Do not place a loose PDB in the cache and expect its identity to be inferred. Use **Asignar PDB propio** or `pdb_local` for explicit validation and recording. Local models are archived with provenance but are not automatically reused in another batch without an explicit selection. A newly chosen manual file is not replaced by an older cached copy.

The original four-column CSV remains supported. `ejemplo_entrada.csv` includes an empty `pdb_local` column. Relative paths in loaded CSV files resolve against the CSV folder; pasted text should use absolute paths. `residuo_inicio,residuo_fin,cadenas` remain optional. Keep field names and accepted values in Spanish.

## Prediction, domains and confidence

The authors document `https://api.esmatlas.com/foldSequence/v1/pdb/`. A real POST with a public sequence was checked, but future availability is not guaranteed. No stable official maximum length was identified; the app uses a **configurable conservative limit of 400 residues**, not a guaranteed service capacity. It does not truncate automatically, split and assemble proteins, or invent models after failure.

For a domain, exactly the requested subsequence is submitted. A response must match sequence and residue count, contain one chain and valid coordinates. The working PDB is renumbered to original positions; JSON records mapping, full/subsequence hashes and isolated-domain provenance. It is not cropped again. The service-returned PDB hash is recorded separately from the renumbered PDB hash.

Predicting an isolated domain **is not equivalent** to cropping a full-protein prediction. Methods are recorded and should be considered when comparing results. Automatic PyMOL contact analysis was not added.

pLDDT uses one Cα per residue and is reported only for known AlphaFold/ESMFold sources, with mean and percentage below 50. Local/experimental PDBs show `NA`. The tested ESMFold endpoint returns historical 0–1 B-factors: when all values are in that range, metrics are multiplied by 100 and `confidence_input_scale` is recorded. This scale is inferred from source and value range; original file B-factors are retained. Warnings remain warnings and neither block docking nor constitute experimental validation.

## Reports and reproducibility

`structure_report.csv` contains one row per protein: input, accession, type, source, pLDDT, percentage below threshold, range, hash, path, status, detail and cache use. Statuses are `OK`, `FALLBACK_OK`, `NEEDS_MANUAL`, `RETRY_PENDING`, `INPUT_ERROR`, `FAILED` or `PENDING`. `needs_manual_modeling.txt` lists problems with statuses; `RETRY_PENDING` requests another lookup, not necessarily manual modeling. Both update throughout preparation; the console prints the final summary.

`pipeline_config.json` preserves app version, UTC dates, options, provenance and SHA-256 for input/prepared models. Batch PDBs are independent cache copies. Historical hashes/jobnames/tokens remain unchanged. Older batches without new metadata may show `Desconocida` (unknown); confidence is not invented retroactively.

## CLI

Open the GUI without fallback:

```powershell
.venv\Scripts\python app.py --no-fallback
```

Prepare structures without docking computation or submission:

```powershell
.venv\Scripts\python app.py --prepare-csv entrada.csv --output lote_nuevo --taxon 9606 --allow-fallback
```

`--allow-fallback` is the default. `--no-fallback` restricts automatic retrieval/cache to AlphaFold while retaining explicit local PDBs, name resolution and reports. The CLI uses the initial source order for new batches; GUI settings can change it afterward. `--esm-max-length 400` is configurable, but increasing it does not guarantee service acceptance. Resume a CLI batch with **Abrir lote guardado** in the GUI.

## Privacy and limits

ESMFold is remote: this feature sends the full sequence or requested domain to its server. Disable it for sequences that must not be shared and use a local PDB from a modeling installation configured not to transmit sequences. A cloud notebook is not local modeling. This feature does not install local ColabFold/ESMFold, and structure preparation does not submit HDOCK jobs.

Failures are not hidden with fictitious PDBs. Obtaining a structure does not guarantee docking quality, correct interfaces, glycans, oligomeric state or appropriate biological regions. Review models and use suitable experimental controls.

Sources: https://github.com/facebookresearch/esm/blob/main/README.md, https://github.com/facebookresearch/esm/blob/main/esm/esmfold/v1/esmfold.py, https://www.uniprot.org/help/accession_numbers, https://www.ncbi.nlm.nih.gov/books/NBK25497/.
