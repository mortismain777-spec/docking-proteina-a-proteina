# Configure free structure sources — 0.4.0

**English** | [Español](CONFIGURACION_PROVEEDORES.md) · [Main guide](README.md)

## First use

1. Restart Docking Matrix from your desktop shortcut.
2. Click **⚙ Configuración** at the upper right, outside the pipeline tabs.
3. Select a source and use **↑ Subir** (move up) or **↓ Bajar** (move down). **Activar / desactivar** enables/disables it. At least one source must remain enabled.
4. Save. Preferences persist across restarts and are copied into each new batch.
5. Keep **Permitir fuentes alternativas según Configuración** checked in the protein tab to allow alternatives.

The initial order is **AlphaFold DB → PDB / PDBe → SWISS-MODEL Repository → ESMFold**. You can put ESMFold before PDB/SWISS-MODEL to predict before searching existing structures. An explicitly selected local PDB takes precedence. With the general alternatives checkbox disabled, only AlphaFold is used automatically, regardless of the configured order.

## Cache and temporary errors

**Usar caché validada antes de consultar las fuentes** uses validated cache entries before remote requests. Only enabled sources are considered, in their chosen order. A cached entry from a lower source can avoid querying a higher source remotely: cache-first behavior is explicit. To require fresh requests in your chosen order, disable this option and create a new batch; the cache is not deleted.

**Probar la siguiente fuente tras agotar reintentos de errores temporales** allows the next source after exhausted retries for 504, 503, 429 or timeout. The failure remains `RETRY_PENDING` in the trace and is not treated as proof that the protein does not exist. When disabled, acquisition for that protein stops at the first exhausted temporary failure. Bounded retries, backoff and `Retry-After` remain in effect.

An existing batch retains its policy until explicitly changed. To change only pending structures, check **Aplicar también a estructuras pendientes del lote abierto**, save and click **Reintentar preparación que falló**. This does not replace prepared structures, change hashes or resubmit HDOCK jobs. Use a new batch to compare sources for proteins already prepared.

## Included sources

| Source | Type | Access |
| --- | --- | --- |
| AlphaFold DB | Precomputed model | Public download; existing canonical selection and cropping. |
| PDB / PDBe | Existing experimental structure | PDBe/SIFTS API and RCSB coordinates; no account or billing. |
| SWISS-MODEL Repository | Existing homology model | Public repository API; no token or newly submitted modeling job. |
| ESMFold | New prediction from sequence | Public endpoint; transmits the sequence. Configurable conservative app limit of 400 residues. |

No billed services have been added. **New modeling through SWISS-MODEL Workspace is not implemented**; it requires account/token configuration and is not presented as a working provider. RefSeq accessions remain supported through ESMFold. Automatic PDB and SMR acquisition require canonical UniProt and do not silently substitute isoforms.

## Conservative selection

PDB queries PDBe's best structures, selects a chain and uses SIFTS to map `label_seq_id` to UniProt positions rather than confusing author numbering with sequence numbering. It requires exact identity and Cα coverage of **every requested residue**. Mutations, gaps and ambiguous mappings are rejected; missing residues are not rebuilt. At most eight candidates per protein are inspected. Coordinates are retained, the first model/conformation is selected, and entry, chain, resolution, method and source hash are recorded. Gemmi reads mmCIF; it is not parsed as PDB text.

SMR requests use `provider=swissmodel` and accept only `SWISSMODEL` entries, excluding AlphaFold mirrors and PDB entries. Candidates covering the region are prioritized by GMQE; up to five distinct templates are inspected, with coordinate sequence/numbering checks. Repository models may cover only part of a protein.

An automatically selected chain does not determine the appropriate biological state. Copies exclude other chains, ligands and cofactors, consistently with preparation. Review conformation, domains, oligomerization and modifications. A structure taken from an experimental complex can introduce prior interface information into docking evaluation.

## Visible provenance

In **Resultados y modelos**, select a row and click **Ver procedencia del par**. Ligand and receptor source, method, entry/chain/template/URL, pLDDT and other metrics appear separately. Structure source is independent of docking engine.

Tables/exports add `Metodo_Ligando`, `Metodo_Receptor`, `Origen_Ligando`, `Origen_Receptor`, `Calidad_Ligando` and `Calidad_Receptor`. `structure_report.csv` includes method, entry, quality and provider trace. `pipeline_config.json` preserves policy and attempts for each protein.

Experimental B-factors **are not pLDDT**. SMR's GMQE and `QMEAN.avg_local_score` are likewise not converted to pLDDT: they are displayed separately, leaving pLDDT empty/NA. Historical provenance is recovered from stored metadata without rebuilding pairs; unknown values remain explicit.

## Official sources

- https://www.ebi.ac.uk/pdbe/api/doc/sifts.html
- https://www.rcsb.org/docs/general-help/website-faq
- https://swissmodel.expasy.org/docs/repository_help
- https://github.com/facebookresearch/esm
- https://gemmi.readthedocs.io/en/latest/cif.html
