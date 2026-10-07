# QSOL Workbench handoff — start here

Prepared for Trent / QSOLKCB on 7 October 2026. Working name: **QSOL Workbench**.

This bundle contains a full design report, a runnable reference implementation, source-review evidence, test evidence, and a staged implementation plan. It is a prototype and handoff package, not a completed replacement for all QEC interfaces.

## For the receiving ChatGPT instance

Read these in order:

1. `HANDOFF_PROMPT.md` — task, constraints, current implementation, next steps.
2. `REPORT.md` — project review, architectural recommendation, alternatives, risks.
3. `docs/IMPLEMENTATION_PLAN.md` — milestones and acceptance gates.
4. `README.md` — run the software and configure integrations.
5. `docs/PROTOCOL.md` and `docs/VALIDATION.md` — actual contract and evidence boundaries.

The source in `src/qsol_workbench/` is executable. Do not treat it as pseudocode. The historical proposal to use Rust/Ratatui is preserved as a production option; this handoff uses Python's standard library to provide a runnable baseline without installing third-party packages.

## Fastest verification

```sh
python3 tools/verify_bundle.py
python3 workbench.py discover
python3 workbench.py run demo.experiment --params '{"steps":3,"seed":7,"delay":0}'
python3 workbench.py web
```

The demo result should contain `"total": 42` and `"demo": true`. Open the local URL printed by the web command, including its token fragment. Or run `python3 workbench.py tui` in an interactive terminal with curses support.

## Files accompanying this directory

- `qsol-workbench-handoff.zip`: the entire handoff.
- `qsol-workbench-handoff.zip256`: SHA-256 checksum in standard `sha256sum` text format.

Verify the archive before extraction with `sha256sum -c qsol-workbench-handoff.zip256` from the directory containing both files. The checksum detects changed bytes; it is not a digital signature. The extracted directory also contains `MANIFEST.sha256` for individual file verification.

## Important scope distinctions

- Demo, shared execution, terminal UI, local web UI, run records, refresh, and cancellation are implemented.
- QEC benchmark argument discovery is implemented and tested against an isolated QEC-shaped fixture. No full QEC scientific installation was executed during this handoff.
- CONTROL capability discovery and health were exercised against the real public CONTROL source snapshot.
- The local Ollama adapter was tested against a local HTTP fixture; no real model weights were loaded.
- Browsh embedding, RIVET rendering, a Rust port, PROVENANCE integration, MACH integration, remote multi-user service, and advanced inference workflows remain roadmap items.

No remote repositories were modified or published.
