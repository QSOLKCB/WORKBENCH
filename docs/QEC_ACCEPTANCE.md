# P1: real QEC acceptance

This gate runs the actual QEC ququart evidence battery through its direct CLI, WORKBENCH CLI and a real Chromium browser form. WORKBENCH's adapter and shared Runtime remain the execution path; acceptance tooling lives outside the base runtime.

## Pinned environment

- QEC repository: <https://github.com/QSOLKCB/QEC>, commit `7103836d731a869dc82b077bc0b920a76072f08e`, package 173.0.0.
- Tested local platform: Linux x86_64, CPython 3.12.14 in a clean venv with no inherited site packages.
- QEC base requirements: NumPy 2.3.5 and SciPy 1.17.0. Exact CPython 3.12 Linux wheel hashes are in [qec-p1-requirements.txt](../examples/qec-p1-requirements.txt).
- Local browser: Chromium 153.0.8010.0; Node 24.19.0. CI uses its installed Chrome and records the actual engine version.
- Workload: trials=40, harmonic_trials=30, seed=31, error_rates=`0.001,0.01`; see [qec-p1-lock.json](../examples/qec-p1-lock.json).

QEC's [INSTALL.md](https://github.com/QSOLKCB/QEC/blob/7103836d731a869dc82b077bc0b920a76072f08e/INSTALL.md) recommends development/science extras for its full test suite. This acceptance installs the base package and its declared base dependencies. Additional science/external backends and the full QEC test suite are outside this workload. The runner requires `pip check` to pass and checks every installed QEC Python source file against the pristine pinned checkout.

## Prepare and run

From the WORKBENCH checkout, with Python 3.12.14 and Node 22 or newer:

```sh
git clone https://github.com/QSOLKCB/QEC.git ../QEC-p1
git -C ../QEC-p1 checkout --detach 7103836d731a869dc82b077bc0b920a76072f08e
python3 -m venv ../qec-p1-venv
../qec-p1-venv/bin/python -m pip install --require-hashes --only-binary=:all: --no-deps -r examples/qec-p1-requirements.txt
python3 -m pip wheel --no-deps --wheel-dir ../qec-p1-wheels ../QEC-p1
../qec-p1-venv/bin/python -m pip install --no-index --no-deps --find-links ../qec-p1-wheels qec==173.0.0
../qec-p1-venv/bin/python -m pip check
python3 tools/qec_acceptance.py \
  --qec-root ../QEC-p1 \
  --python ../qec-p1-venv/bin/python \
  --browser-bin /usr/bin/google-chrome \
  --output ../qec-p1-acceptance
python3 tools/qec_acceptance.py --verify ../qec-p1-acceptance
```

Use the actual Chrome/Chromium executable on your machine. The runner requires a fresh output directory and preserves partial evidence when a command or browser check fails. It removes inherited PYTHONPATH/PYTHONHOME during execution. No browser session token is retained. Output is never copied over a prior run. An optional `--setup-receipt FILE` retains a separate environment-preparation transcript; the checked-in local evidence includes one with commands, build-tool versions and wheel hashes.

The runner executes equivalent commands to:

```sh
../qec-p1-venv/bin/python -m qec.benchmark.ququart_battery.cli --output=NEW_DIRECTORY --trials=40 --harmonic-trials=30 --seed=31 --error-rates=0.001,0.01
python3 workbench.py --config LOCAL_CONFIG --store NEW_STORE run qec.ququart.benchmark --params-file PARAMETER_FILE
../qec-p1-venv/bin/python -m qec.benchmark.ququart_battery.validate_cli --claims NEW_DIRECTORY/report_claims.json --evidence NEW_DIRECTORY
```

For the browser, `tools/qec_browser.mjs` fills the discovered DOM controls and invokes native form submission. It polls the displayed record, saves it and checks both successful and failed outcomes. It does not bypass the form with a direct API request. The server uses `make_server` and the same configured Runtime as normal `workbench.py web`.

## Retained evidence and checks

The [local evidence directory](../evidence/p1-qec/) contains source/package identities, dependency freeze, environment setup, discovery, command argv/cwd/exit/stdout/stderr, three complete artifact directories, four final WORKBENCH records and their disk snapshots, browser receipt, three independent QEC validation receipts, and failed backend/claim-validation outputs.

Each successful directory contains QEC's 14 declared artifacts plus `benchmark_manifest.json`. The runner verifies complete coverage, artifact hashes, canonical manifest/methodology checksums and requested inputs. It requires the direct result and WORKBENCH results to match their disk manifests. No path or timestamp normalization was needed: all three manifests and all scientific artifact bytes were identical.

QEC's validator is run independently on each output; its successful receipt must match the generated claim-validation receipt. An intentionally invalid threshold claim must be rejected. Setting trials=0 must produce the real QEC `trials must be positive` error directly, in CLI and in the browser; WORKBENCH must retain a failed run, nonzero child exit and stderr.

```sh
python3 tools/qec_acceptance.py --verify evidence/p1-qec
```

Offline verification checks the evidence inventory, outcomes, saved record checksums, artifact equivalence and QEC receipt associations without installing QEC or starting a browser. `.github/workflows/p1-qec.yml` separately repeats the real execution against the pinned QEC source and uploads its own complete output, including failed attempts. Checksums establish consistency rather than authenticated provenance; the retained validator receipts are observations, and the CI job reruns the validator.

## Scope

P1 proves this installed QEC workflow's integration in the recorded environment. The tiny Monte Carlo counts are unsuitable for new statistical or scientific claims. QEC's report version 170.1.1 describes the battery contract; package version 173.0.0 describes the installed distribution. QEC includes a historical qBraid replication receipt as an artifact; this acceptance does not rerun qBraid. No Ollama model, hardware quantum execution, full QEC suite, production installation or unfinished TUI adapter panel is validated here.
