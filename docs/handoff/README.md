# QSOL Workbench — executable reference implementation

A small shared action registry and execution layer, presented through a command line, a curses terminal UI, and a local browser interface. Version **0.1.0**.

## Requirements

- Python 3.10 or newer. Validated here with Python 3.14.4 on Linux.
- No third-party Python runtime dependencies for source-checkout execution.
- The terminal UI additionally requires the Python `curses` module and an interactive terminal. Linux is the validated platform. Native Windows terminal support is not claimed; CLI/web may be usable but are untested there.
- Optional backend dependencies remain in their own environments.

Run from this directory. Package installation is optional; `workbench.py` adds `src/` to the Python path. `pyproject.toml` supports packaging, but building a wheel may require obtaining setuptools if it is absent. Packaging installation was not validated in this handoff.

## Run now

```sh
python3 workbench.py --version
python3 workbench.py discover
python3 workbench.py run demo.experiment --params '{"steps":3,"seed":7,"delay":0}'
python3 workbench.py history
python3 workbench.py tui
python3 workbench.py web
```

The demo computes `seed × (1 + … + steps)` and reports progress. It is explicitly labelled DEMO everywhere; it is never substituted for an unavailable scientific backend.

Global flags precede the subcommand:

```sh
python3 workbench.py --store /tmp/my-workbench-runs --timeout 60 run demo.experiment
python3 workbench.py --config examples/config.json web --port 8765
```

The web server binds to `127.0.0.1` only. Use the exact URL it prints. API access requires the per-process token in that URL; the fragment is removed from the address bar after loading. The browser polls job state twice per second. This is a local single-user prototype.

## Terminal controls

| Key | Operation |
|---|---|
| Up/down or j/k | Select an action |
| Tab | Select an input field |
| e | Edit the selected input |
| r | Run the selected action |
| c | Cancel the currently displayed run |
| h | Show the latest saved run |
| f | Refresh connections and capability forms |
| q | Quit and cancel jobs owned by this session |

String input is entered directly; numeric/boolean fields use JSON syntax. Editing is deliberately basic and single-line. The web UI is better suited to longer prompts and full records. Large TUI outputs are clipped to terminal width and the latest visible lines; complete output is retained within the capture limit in the JSON run record.

## Connect QEC

Copy `examples/config.json` to a local configuration file. Enable `qec` and set:

```json
{
  "qec": {
    "enabled": true,
    "python": "/absolute/path/to/QEC/.venv/bin/python",
    "cwd": "/absolute/path/to/QEC"
  }
}
```

The selected interpreter must already be able to import QEC and its required dependencies. The workbench does not install QEC, update it, select a release, or create missing CLI modules.

```sh
python3 workbench.py --config local.json discover
python3 workbench.py --config local.json --timeout 600 run qec.ququart.benchmark \
  --params '{"trials":10,"harmonic_trials":10,"seed":1701001,"output":"/tmp/qec-workbench-example"}'
```

Small trial counts here are a connectivity smoke check, not meaningful research evidence. QEC's own backend determines computation, validation, and artifact meaning.

Only the existing ququart evidence battery is mapped in this prototype. The adapter imports `qec.benchmark.ququart_battery.cli.parser()` inside the selected environment and exports supported arguments. Supported new scalar options appear after **Refresh connections**, or on the next startup. Unsupported parser shapes make the action unavailable with an error; they are not silently omitted. QEC's parser remains responsible for richer domain constraints.

The connection records Python executable, package version (or `unpackaged-checkout`), module path, module source hash, and working directory. The hash covers the CLI module, not the entire backend or its dependencies. QEC output paths are interpreted by QEC; choose a separate output directory for each experiment to avoid backend-defined overwrites.

## Connect QSOL-CONTROL

```json
{
  "control": {
    "enabled": true,
    "argv": ["/usr/bin/python3", "tools/agent_api.py", "--root", "/absolute/path/to/control-store"],
    "cwd": "/absolute/path/to/QSOL-CONTROL"
  }
}
```

Use the interpreter appropriate for that checkout. The adapter speaks the actual `qsol-control-agent-request/1` JSONL envelope and exposes `control.health` and `control.capabilities`. It verifies success protocol, request correlation, operation, and authority. Each request launches a separate API process and closes stdin after one request. This is a limited read-operation integration; it does not provide a persistent session, aggregate CONTROL quotas, council access, or run replay.

CONTROL may initialize its configured storage during startup, even when the requested operation is read-only. Use an explicit storage directory. A complete connection test against CONTROL commit `55c3fbee6435d4a6206aa946579f36724698a20b` is included in the validation evidence.

## Optional local AI playground

With an existing local Ollama server and at least one installed model:

```json
{
  "ollama": {"enabled": true, "url": "http://127.0.0.1:11434"}
}
```

Run `python3 workbench.py --config local.json --timeout 600 web`. Choose **Local model playground**. The module discovers installed model names, accepts a prompt, temperature and seed, streams output, and saves the run. Browser presets save the field values locally. The prototype uses Ollama's `/api/tags` and `/api/generate` endpoints.

This is single-prompt generation, not multi-turn chat, RAG, file ingestion, tool execution, model management, or training. Only loopback HTTP origins are accepted; redirects and inherited HTTP proxies are disabled. No model downloads occur. A seed is a recorded input, not a guarantee that a particular model/backend is deterministic.

Cancellation terminates the local transport worker. It closes the HTTP connection but does not prove that the provider has stopped all server-side computation. Backend-visible response fields are retained in the raw stream; the main UI renders response text.

## Records and limits

Run records are stored in `.workbench/runs/` by default, including inputs, outputs, backend identity, argv, timestamps, exit status, and parsed result. Files are atomically replaced when finalized. A SHA-256 checksum covers the finalized record content excluding the checksum field. This is a local integrity aid, not a signed provenance chain or scientific correctness proof.

- Maximum four active jobs per workbench process.
- Default 120-second run deadline; configurable up to 24 hours.
- Maximum 1 MiB combined captured stdout/stderr per job; exceeding it stops the process and marks `output_limit`.
- Discovery deadline 12 seconds and 256 KiB output limit.
- Web request bodies limited to 64 KiB. Text fields have per-field limits.
- History lists the most recent 100 disk records; the web sidebar shows 15.
- Session memory retains run records until the workbench process exits. There is no retention scheduler or persistent job daemon.

On Linux, cancellation kills the process group to include descendants. Completed backend effects are not rolled back. Graceful exit requests cancellation for owned jobs; abrupt process death can leave the last saved queued record, reported as `interrupted` on the next load. Do not run two workbench processes as simultaneous job managers for the same store; cross-process coordination is not implemented.

Presets and run records can contain prompts, paths, and generated content. Keep private run directories outside a shared handoff. This bundle contains only deliberately generated demo/validation evidence.

## Test and inspect

```sh
python3 -m unittest discover -s tests -v
node --check src/qsol_workbench/static/app.js   # optional syntax check
python3 tools/verify_bundle.py
```

Two tests start loopback HTTP servers; a restrictive execution sandbox must permit local sockets. Optional browser acceptance: start `workbench.py web`, then run `node tools/browser_smoke.mjs 'THE_PRINTED_URL' evidence/browser.png` with Node 22+ and Chrome available. Set `BROWSER_BIN` for another Chrome/Chromium executable. Browser testing is a development dependency only.

## Source map

| File | Responsibility |
|---|---|
| `src/qsol_workbench/model.py` | Input definitions, validation, action/plan model |
| `src/qsol_workbench/adapters/builtin.py` | Demo, QEC, CONTROL and Ollama integration |
| `src/qsol_workbench/worker.py` | Isolated discovery/demo/inference workers |
| `src/qsol_workbench/process.py` | Process transport, capture, deadlines and cancellation |
| `src/qsol_workbench/runtime.py` | Shared registry, jobs and records |
| `src/qsol_workbench/cli.py` | CLI entry point |
| `src/qsol_workbench/tui.py` | Curses presentation |
| `src/qsol_workbench/web.py` | Local HTTP API and static delivery |
| `src/qsol_workbench/static/` | Dependency-free browser presentation |
| `tests/test_workbench.py` | Contract, process, adapter and HTTP behavior tests |

See `REPORT.md` for the architectural assessment and `docs/IMPLEMENTATION_PLAN.md` for the path beyond this reference implementation.
