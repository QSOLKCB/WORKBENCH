# Instructions

[Complete usage](docs/USAGE.md) covers QEC, CONTROL, Ollama, terminal controls, saved records and limits. Global options precede the subcommand:

```sh
python3 workbench.py --config local.json --timeout 600 web
python3 workbench.py --store /tmp/workbench-runs run demo.experiment
python3 workbench.py show RUN_ID
```

Validate a checkout:

```sh
python3 tools/verify_bundle.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests tools workbench.py
node --check src/qsol_workbench/static/app.js
node --check tools/browser_smoke.mjs
node --test tests/browser_values.mjs
```

Tests require local sockets for HTTP fixtures. Node is a development tool, not a runtime dependency. Optional browser acceptance also requires Chrome/Chromium; see [usage](docs/USAGE.md).

After changing repository files, run `python3 tools/build_bundle.py` to regenerate `MANIFEST.sha256` and a deterministic archive/checksum outside the checkout, then `python3 tools/verify_bundle.py`. The manifest covers the current repository; the historical manifest under `docs/handoff/` covers the original uploaded archive.

Verify retained QEC evidence without installing QEC:

```sh
python3 tools/qec_acceptance.py --verify evidence/p1-qec
python3 tools/qec_p2_acceptance.py --verify evidence/p2-qec
```

Repeat current QEC/Chromium execution using [P2 acceptance instructions](docs/QEC_DESCRIPTORS.md), or the original [P1 gate](docs/QEC_ACCEPTANCE.md). Phase status is in [ROADMAP.md](docs/ROADMAP.md).
