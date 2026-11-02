# Validation record and limitations

**English** | [Español](VALIDACION.md) · [Main guide](README.md)

This is a historical record of checks. Later sections update the initial limitations; successful software checks do not validate scientific predictions.

## Initial version — October 30, 2026

Checks using Python 3.12 on Windows:

- 12 passing automated tests (`python -W error::ResourceWarning -m unittest -v`), covering matrix/controls, partial failures, ambiguous resolution, simulated retrieval, scores, export, a real test subprocess, resuming and token reconciliation.
- Module compilation and Python 3.9-compatible syntax analysis. The suite was not run on a Python 3.9 interpreter.
- Tkinter opened all three tabs without exceptions. Native screenshot capture failed in the test environment, leaving manual visual review pending at this stage.
- A real UniProt query resolved `EGFR`, TaxID 9606, to reviewed entry `P00533`.
- AlphaFold `P69905` was downloaded and validated with SHA-256. Windows trusted CAs were incorporated into a temporary bundle while retaining TLS verification.

At this stage, no real HDOCK jobs were submitted and the external engine was not installed; CLI behavior used a simulated engine. Scores were parsed from representative synthetic HTML, with unknown formats leaving a URL and empty score. No scientific validation was performed; albumin and ubiquitin were provisional references. A single real pair and a manually checked score were recommended before a large batch, keeping batch data outside version control.

## November 1, 2026 update

- The external engine, Playwright and Chromium were installed. The user successfully submitted two HDOCK jobs and received tokens.
- Parsing of row-oriented scores was corrected and verified against both real result pages.
- The UI, examples and exports changed `RBP` to `Ligando`, retaining legacy CSV/batch compatibility and identifiers, structures, tokens and scores.
- 15 passing automated tests. The old batch reopened with its two scores preserved, without modification or resubmission.
- A project-local Chromium installation was supported to avoid relying on another execution context's cache.

These checks validate workflow behavior rather than score interpretation or the suitability of controls.

## PD-1 / PD-L1 / CD80 experimental example

Albumin/ubiquitin became optional for new batches. Optional `residuo_inicio,residuo_fin` cropping and exact canonical model selection among AlphaFold isoforms were added.

Real downloads prepared human Q15116 (25–170), Q9NZQ7 (19–238) and P33681 (35–242): three structures, two pairs, zero errors, no local PDB overrides and no new docking submissions. The [protocol](protocolo_PD1_PDL1_CD80.en.md) records the contextual negative reported by Freeman et al. (2000), construct differences and limits of unglycosylated models without Ig fusions.

Tests cover isoform selection, cropping, residue coverage, bound validation, reference exclusion and protecting a batch against changed ranges. The panel was prepared for an exploratory test; docking had not been run for it at this stage.

## Local mode, downloads and notifications

- 30 passing automated tests, including heavy-atom preparation/geometry, model extraction, coordinate preservation, engine isolation, resuming and notifications without duplicates or waiting alerts.
- Five models downloaded from each of two completed HDOCK jobs: 10 originals and 10 viewer copies, without resubmission or changes to the original batch. Structural opening was verified through ChimeraX 1.12's command-line interface.
- A separate monitor process read jobs, saved tables/results and stopped once models were available. Duplicate-monitor exclusion and notification state persistence per token were checked.
- Windows-Toasts was installed in the virtual environment. Windows accepted a test notification request; actual visibility remains dependent on Windows preferences, without forcing system notifications on.
- Native screenshots were used to review the execution tab. Local/server modes opened, historical scores remained and updated labels appeared.
- The PD-1 panel used real structures with 146/220/208 residues, three working copies, two pairs and no errors, recording pLDDT statistics and dimensions.
- The local adapter ran simulated `hdock`/`createpl` subprocesses, generated PDBs and resumed without mixing server tokens. Official HDOCKlite executables were downloaded outside the distributed code. **A real HDOCKlite calculation has not yet been verified on this computer**: WSL/Ubuntu setup and first launch must be completed, with elevation/restart if requested by Windows.

Preparation automates cleanup, unambiguous selection and traceability. It does not guarantee appropriate biological domains, rebuilt missing regions, glycans, specific protonation, minimization or experimental validation. HDOCKlite performs a global search; no fictitious grid box is offered, and its protocol is not equated with the server's hybrid protocol.

## Alternative acquisition — 0.3.0

- 41 passing automated tests, including the previous 30. Coverage includes prediction-vs-PDB-download 404s, temporary errors without fallback, retry counts/`Retry-After`, versioned RefSeq, sequence identity, domain numbering, limits without truncation, corrupt cache, offline reuse, local files with NA confidence and partial reports without docking logs.
- A real POST to the official ESMFold endpoint with a public ubiquitin sequence returned HTTP 200 and a valid PDB. GET returned 403, so predictions are not blocked by an incompatible GET probe.
- Real NCBI RefSeq `NP_061828.1` → subsequence 77–152 → ESMFold: 76 residues, restored original numbering, normalized mean confidence 90.5395/100 and 1.3158% below 50. The response used 0–1 B-factors; inference was recorded and only metrics normalized, preserving the PDB. A regression test covers the scale difference.
- The same technical batch downloaded AlphaFold Q15116 (25–170): 146 residues, mean pLDDT 85.9441. One pair was prepared without docking submission/computation. This combination checks software, not a proposed positive interaction or control.
- Both real structures were recovered from cache using a client that rejects network access: two hits and zero calls. GUI startup with fallback disabled and 18 result columns was checked; the protein-tab checkbox and stop button were visually reviewed.
- Future service availability and official maximum length are not guaranteed; 400 residues is an application-level conservative limit. No local predictor was installed. These checks do not establish interface quality or affinity accuracy.

## Free providers and settings — 0.4.0

- 50 passing automated tests: the previous 41 plus chosen order, disabled providers, fallback after 504, stopping on temporary failures, ordered cache, no-fallback, SIFTS mapping, mutation/gap rejection, GMQE/pLDDT separation, policy persistence and historical views without jobname mutation.
- Real retrieval for P69905, region 2–142: PDB 1BZ1 chain A (1.59 Å resolution) and a SWISS-MODEL Repository model based on 9vic.3.A (GMQE 0.902; `QMEAN.avg_local_score` 0.836). Both had 141 residues with exact sequence; pLDDT remained NA.
- Two technical cache-only batches with opposite provider orders each chose their priority source, generated one pair and had zero errors. No `run-log.csv` was created and no docking was submitted. The same protein in both roles was a software check rather than an interaction claim.
- The gear button/source dialog was visually reviewed and **Bajar** changed the order. The test was canceled without changing user preferences. The dialog is explicitly centered.
- No billed services or accounts/tokens were added. SWISS-MODEL Repository downloads existing models; new Workspace modeling is not implemented. Gemmi 0.7.5 was installed from PyPI for mmCIF reading.
