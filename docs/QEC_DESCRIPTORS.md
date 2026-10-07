# P2: backend-owned QEC capabilities

QEC companion [PR #595](https://github.com/QSOLKCB/QEC/pull/595) provides `qec-capabilities/1`. Merge that companion before adopting WORKBENCH's native default. The acceptance pin is QEC commit `51dd1ae9fe00a142af4b39a38c46deba2f8aca45`, package 173.0.0; a package version alone cannot distinguish this descriptor-capable build from the P1 build.

## Operator setup

Install the pinned source into a separate QEC environment. Run from the WORKBENCH checkout with CPython 3.12.14 on Linux x86_64:

```sh
git clone https://github.com/QSOLKCB/QEC.git /tmp/qec-p2
git -C /tmp/qec-p2 checkout 51dd1ae9fe00a142af4b39a38c46deba2f8aca45
python3 -m venv /tmp/qec-p2-venv
/tmp/qec-p2-venv/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r examples/qec-p1-requirements.txt
python3 -m pip wheel --no-deps --wheel-dir /tmp/qec-p2-wheels /tmp/qec-p2
/tmp/qec-p2-venv/bin/python -m pip install --no-index --no-deps --find-links /tmp/qec-p2-wheels qec==173.0.0
/tmp/qec-p2-venv/bin/python -m pip check
/tmp/qec-p2-venv/bin/python -m qec.capabilities
```

Use a local configuration:

```json
{"demo":{"enabled":false},"qec":{"enabled":true,"discovery":"descriptor","python":"/tmp/qec-p2-venv/bin/python","cwd":"/tmp/qec-p2"}}
```

`python3 workbench.py --config local.json discover` exports three operations. The same forms appear in TUI and web. Keep the configured interpreter and cwd fixed for the session; refresh after changing the backend.

| Action | Inputs | Result |
|---|---|---|
| `qec.ququart.benchmark` | Output directory, trials, harmonic trials, seed, error rates | Ququart artifact manifest |
| `qec.ququart.validate` | Required claims file and evidence directory; optional test receipt and output file | QEC claim-validation receipt |
| `qec.qutrit.benchmark` | Output directory, historical baseline file, stress limit | Qutrit artifact manifest |

All path inputs retain QEC's cwd-relative semantics. The qutrit baseline default names `qec_data_prepared.csv` in the configured checkout. Use a new output directory per benchmark. Optional validator output writes a receipt file; its parent directory must exist, as required by QEC's CLI.

## Contract and compatibility

QEC's public parsers and metadata share `ScalarOption`/`CommandSpec` declarations. The lightweight export does not import scientific CLI modules or inspect argparse internals. QEC remains responsible for scientific computation, artifact assembly and domain validation.

The descriptor contains `protocol`, `implementation_modules`, and `actions`. Each action declares its reviewed module, fields, effect and output. Scalar fields support string, integer, number and boolean types, converted defaults, requiredness, typed choices and numeric bounds. Shared QEC converters reject out-of-range inputs during direct CLI parsing before artifact writes. Path strings additionally declare `path_role` (`read-file`, `read-directory`, `write-file`, `write-directory`) and `path_base: cwd`. Boolean argv values are literal `true`/`false`, matching QEC's shared scalar converter.

Unknown protocols, custom/list/nargs inputs, malformed defaults/choices, unsupported path semantics and unreviewed command modules make the connection unavailable with an error. The registry deliberately reviews entry points and output schemas; adding a new action or richer protocol requires an adapter change. Adding a supported scalar field to an existing command requires no frontend change.

WORKBENCH reads the provider, shared declarations and command source hashes from the imported package without importing scientific CLI modules for discovery. Capability identities include these hashes, the descriptor digest, interpreter, cwd and owning distribution version. Same-named unrelated distribution metadata is ignored. `unpackaged-checkout` is used when distribution ownership cannot be established. These are local consistency observations, not authenticated provenance or a complete dependency fingerprint. External backend changes after discovery remain possible.

`discovery` defaults to `descriptor`. Older QEC installations report the missing export explicitly. To reproduce P1 against its original source pin, select `"discovery":"legacy-argparse"`; that mode publishes only the ququart battery and retains the temporary parser bridge. There is no automatic compatibility fallback. P1's evidence remains unchanged, and its CI uses this explicit legacy setting.

The shared Runtime enforces each native result's declared JSON schema, and requires `passed: true` for validation receipts. A zero-exit protocol failure retains transport diagnostics but is a failed run. The browser renders artifact names/hashes and validation receipts through generic output contracts. Artifact views label the contents as backend-reported; displaying them does not independently verify or download files. Raw stdout, stderr and the complete record remain available.

## Acceptance and retained evidence

```sh
python3 tools/qec_p2_acceptance.py \
  --qec-root /tmp/qec-p2 --python /tmp/qec-p2-venv/bin/python \
  --browser-bin /usr/bin/google-chrome --output /tmp/p2-qec-evidence
python3 tools/qec_p2_acceptance.py --verify /tmp/p2-qec-evidence
python3 tools/qec_p2_acceptance.py --verify evidence/p2-qec
```

The output directory must be new. Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, Node 22+ and Chrome/Chromium are the tested acceptance matrix. Node and the browser are optional development tools. WORKBENCH retains its standard-library-only runtime.

The runner checks a pristine pinned checkout, every installed QEC Python source file, `pip check`, backend export, all three direct/CLI/real-browser commands, saved records and generic browser views. Ququart runs use trials 40, harmonic trials 30, seed 31 and rates `0.001,0.01`; qutrit uses stress limit 8 and the immutable historical baseline. Each interface writes separate outputs. All 15 ququart and 13 qutrit files per mode match byte for byte; QEC's validator returns identical successful receipts. No path or timestamp normalization is needed.

`test_qec_descriptors.py` separately proves that a new supported field updates the fixture's public CLI and refreshed manifest; stale HTTP submission is rejected without starting a job; new values survive execution; unsupported shapes never fall back. Node fixtures prove refreshed forms use the new field/fingerprint and that structured views render as text. Their transcripts are retained as fixture evidence, distinct from the installed QEC scientific runs. Existing P1 negative execution/claim evidence remains available.

The evidence includes commands, environment/dependency versions, QEC and WORKBENCH source inventories, direct outputs, scientific artifacts, persisted runs, browser receipts and a complete checksum inventory. The offline verifier checks content and consistency; it does not rerun QEC. CI repeats real execution and uploads fresh evidence for the PR commit. Small trial/stress counts establish integration only. QEC's own scientific claim restrictions continue to apply; full QEC test-suite, hardware, real-model inference and production packaging gates are unchanged.
