# Source provenance and licensing

WORKBENCH uses the repository's Apache-2.0 [LICENSE](../LICENSE). The Phase 0 implementation was imported from Trent's Astra handoff on 7 October 2026, then adapted for this repository with documentation organization, package identity, CI and saved-record verification.

Original archive: `qsol-workbench-handoff.zip` (40 files).

SHA-256: `10f059ee1ee9268ddfaa0fd6bf6d5dbb71d709eea64bc6e1f011c4b3f433b692`.

The external checksum matched and the original internal manifest verified all 39 covered files before import. `handoff/MANIFEST.sha256`, `handoff/README.md`, `handoff/START_HERE.md`, `handoff/HANDOFF_PROMPT.md` and `handoff/LICENSE-NOTE.md` preserve historical handoff text verbatim. Their paths and licensing-selection language describe the original archive, before the Apache-2.0 repository import. The root manifest describes the current checkout.

Original evidence remains under `../evidence/`; its transcripts, absolute paths and source snapshots describe Astra's validation environment. Repository validation additions are recorded separately in [VALIDATION.md](VALIDATION.md).

External source URLs, commits and hashes are recorded in `../evidence/sources.json`; no external codebases or model weights are bundled. QEC/CONTROL run in operator-installed environments. Ollama is an optional local HTTP provider. Python's standard library and native browser APIs provide the runtime; Node and Chrome are optional development tools.

Future source imports must retain their own donor licenses and notices. Architecture similarities and checksums do not establish source ownership or a license.
