# Docking test with a contextual experimental negative

**English** | [Español](protocolo_PD1_PDL1_CD80.md) · [Main guide](README.md)

## Question

Does the workflow record pairs correctly, and what poses/scores does HDOCK produce for a known positive interaction and a pair reported to show no detectable binding in a published assay?

## Experimental evidence

Freeman et al. (2000), *Engagement of the PD-1 Immunoinhibitory Receptor by a Novel B7 Family Member Leads to Negative Regulation of Lymphocyte Activation*, J. Exp. Med. 192:1027–1034.

https://pmc.ncbi.nlm.nih.gov/articles/PMC2193311/

The study detects human PD-1 / PD-L1 interaction using cytometry and SPR/BIAcore with Ig fusion proteins. It reports that soluble human B7-1/CD80 and B7-2/CD86 did not bind immobilized human PD-1. These negative observations are described in the text but the data are not shown. This does not establish absolute absence of interaction under every condition or an unpublished numerical affinity limit.

## Human panel

| Computational role | Protein | UniProt | Extracellular region |
| --- | --- | --- | --- |
| Common ligand | PD-1 | Q15116 | 25–170 |
| Positive receptor, A | PD-L1 | Q9NZQ7 | 19–238 |
| Contextual negative receptor, control | CD80/B7-1 | P33681 | 35–242 |

Region sources: canonical UniProt Topological domain / Extracellular annotations, consulted November 1, 2026:

- https://www.uniprot.org/uniprotkb/Q15116/entry
- https://www.uniprot.org/uniprotkb/Q9NZQ7/entry
- https://www.uniprot.org/uniprotkb/P33681/entry

These are extracellular regions from canonical AlphaFold models rather than exact replicas of Fc-containing experimental constructs. Signal peptide, transmembrane segment and cytoplasmic tail are excluded. Both pairs use the same PD-1 region. Glycans and experimental Ig fusions are not modeled. Candidate sizes/compositions differ, and docking scores are not direct affinity measurements.

## App procedure

1. Restart the updated app and load `prueba_PD1_PDL1_CD80.csv`.
2. Leave albumin and ubiquitin unchecked. Organism: 9606. Email is optional. Do not assign local PDB overrides.
3. Create a new batch. Check three structures, two prepared pairs and zero errors. The CSV supports automatic download/cropping without manual PDB editing.
4. Inspect `pipeline_config.json`: models, ranges, sources and SHA-256. Keep this batch separate from the barnase/barstar example.
5. Submit the two pairs once, using the same engine, interval and parameters. Do not reuse tokens from other batches.
6. Poll until scores are available and export the complete table.
7. Click **Consultar HDOCK y descargar modelos** or activate background monitoring. The app downloads available models for ChimeraX/PyMOL. Check composition, coverage and the PD-1 region in each.
8. For the positive, compare the interface with a human experimental structure such as [4ZQK](https://www.rcsb.org/structure/4ZQK). It contains a mutated PD-1 construct and requires sequence correspondence checks.

## Predefined interpretation

No expected numerical score difference or cutoff is specified. As an exploratory hypothesis, the positive could score more negatively, but HDOCK discrimination is not guaranteed. If the negative scores favorably, review pose, domains, template use, coverage, omitted glycans and method scope. Do not redefine the negative as positive solely because of docking.

The control represents no detectable binding in the cited assay. Two pairs do not establish sensitivity/specificity or validate a general interaction predictor.
