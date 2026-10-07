# WORKBENCH

**A capability-driven project workspace.** CLI, curses TUI and a local browser interface share backend discovery, typed inputs, validation, bounded execution and run records.

[![Version](https://img.shields.io/badge/version-0.1.0-4c1.svg)](CHANGELOG.md)
[![Phase](https://img.shields.io/badge/phase-0-2ea44f.svg)](docs/IMPLEMENTATION_PLAN.md)
[![CI](https://github.com/QSOLKCB/WORKBENCH/actions/workflows/phase0.yml/badge.svg)](https://github.com/QSOLKCB/WORKBENCH/actions/workflows/phase0.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Start here:** [Getting started](GETTING_STARTED.md) · [Instructions](INSTRUCTIONS.md) · [Protocol](docs/PROTOCOL.md) · [Roadmap](docs/IMPLEMENTATION_PLAN.md) · [Validation](docs/VALIDATION.md)

```sh
python3 workbench.py discover
python3 workbench.py run demo.experiment --params '{"steps":3,"seed":7,"delay":0}'
python3 workbench.py tui
python3 workbench.py web
```

Requires Python 3.10+. Source execution uses the standard library; TUI requires curses and an interactive terminal. The web server binds to loopback and prints its authenticated local URL.

Phase 0 imports Astra's executable reference baseline: shared runtime, demo, QEC parser bridge, CONTROL read operations, optional Ollama streaming, tests and original evidence. Saved disk records are checked before display. [Architecture report](docs/REPORT.md) and [source provenance](docs/SOURCE_PROVENANCE.md) document the handoff.

QEC execution is fixture-tested; a real scientific workflow is the P1 gate. Ollama is HTTP-fixture-tested. Original CONTROL evidence exercised a real source snapshot. Jobs belong to one local session; cross-process coordination and durable background jobs remain planned.
