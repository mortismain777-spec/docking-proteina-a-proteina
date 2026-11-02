# Local computation with HDOCKlite

**English** | [Español](INSTALACION_LOCAL.md) · [Main guide](README.md)

Local mode runs global ab initio HDOCKlite. It does not require a manual grid box: it explores relative positions and orientations. Reported dimensions describe structures rather than a search box or pocket optimization. The web server can use templates, so local and server modes must not be treated as one protocol.

## Windows: install WSL once

1. Save your work and open PowerShell **as administrator** from Start.
2. Run `wsl --install` following the [official guide](https://learn.microsoft.com/windows/wsl/install).
3. Restart only if Windows requests it. The app does not restart your computer automatically.
4. Open Ubuntu and complete first-time setup with a username and password. Do not share the password in chat.
5. Check `wsl --list --verbose` and `wsl --exec uname -m` in PowerShell. The supported official HDOCKlite binaries require Linux x86-64.

Downloading binaries does not replace WSL. If elevation, virtualization or a restart is required, the app reports it instead of simulating a local calculation.

## Install or prepare the engine

First read the [official HDOCKlite terms](https://github.com/huang-laboratory/HDOCKlite/blob/main/LICENSE.txt). They allow academic/noncommercial use and restrict redistribution outside the group or laboratory; ask its authors about commercial use. Docking Matrix does not distribute these executables.

From the project folder, after reviewing whether your use is authorized:

```powershell
.venv\Scripts\python setup_local.py --download --license-reviewed
```

If the files are already in `tools/hdocklite`, prepare permissions and check them with:

```powershell
.venv\Scripts\python setup_local.py
```

For a particular WSL distribution, add `--distribution Ubuntu`, substituting its actual name. Paths are converted with `wslpath`; argument lists are used without constructing shell commands from protein names.

On native Linux, use `python3 setup_local.py --download --license-reviewed`. WSL is unnecessary. Install any missing runtime libraries reported by the Linux loader for the official binary.

## Use local mode

1. Enter names, genes or accessions and the appropriate TaxID. Resolve ambiguous names with a UniProt ID.
2. Prepare a new batch. Use full structures or an unambiguously annotated extracellular region, or provide residue bounds/chains in the CSV.
3. Review preparation reports and warnings. Automatic cleanup does not rebuild residues, add glycans, determine biological assemblies or validate an experimental hypothesis.
4. Select **Este equipo · HDOCKlite** in tab 2, set `tools/hdocklite`, then click **Comprobar motor local** (check local engine).
5. After reviewing the license, check its acknowledgement box and click **Calcular pares en este equipo** (calculate pairs locally).
6. Models and tables are stored in `local/` and `resumen_local.*`. There are no HDOCK tokens because local docking does not submit PDB files to the server.

Initial software and structure downloads require Internet. With input PDB files and the engine installed, local docking does not use the server. One pair runs at a time to limit resource consumption; runtime depends on hardware and structures and must be measured.

**Pausar tras el par activo** lets the current calculation finish and saves its result before stopping the next pair. Keep the GUI open during local computation. Local and server results are stored separately and do not share a ranking.
