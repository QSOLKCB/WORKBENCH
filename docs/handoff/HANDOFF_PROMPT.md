# Prompt for the receiving ChatGPT instance

You are receiving a design and working-code handoff for Trent / QSOLKCB's proposed reusable frontend. Read `START_HERE.md`, `REPORT.md`, `README.md`, `docs/PROTOCOL.md`, `docs/IMPLEMENTATION_PLAN.md`, and `docs/VALIDATION.md` before proposing changes.

## User's original intent

Improve an idea for a clean Browsh-inspired frontend that can attach to QEC and other projects, offer a TUI/ncurses-style experience, optionally support an advanced AI inference web UI, live in a small modular monorepo, and avoid continual drift between a project's current commands/release and its frontend.

The user supplied https://github.com/QSOLKCB as the public source collection and requested a full report plus an implementation if possible, bundled as ZIP with a `.zip256` checksum.

## Recommended direction

The proposed product is **QSOL Workbench**: a capability-driven project workspace. Share typed operation definitions, backend discovery, input validation, execution and records. Use terminal and browser presentations over the same core. Keep Browsh viewing, RIVET rendering, PROVENANCE integration and MACH execution optional.

Do not restart the architecture discussion from a blank page. Review the delivered implementation and the evidence, then improve the smallest incomplete real workflow.

## Source findings to preserve

1. QEC's reviewed TUI calls five Python diagnostic/history/law adapter modules that the reviewed repository does not ship. Its current usage guide acknowledges this. A new frontend does not automatically implement those modules.
2. The curl installer is fetched from `main`, but it installs/builds the latest release tag. At review time that release was `v173.0` with no uploaded assets. Fixes on `main` can therefore be absent from the installed TUI.
3. Current QEC source already derives the TUI displayed version from `pyproject.toml` and tests it. Preserve that improvement; do not diagnose the Rust Cargo package version in isolation.
4. QEC exposes actual command entry points. The ququart battery parser and JSON manifest output are the initial adapter target.
5. CONTROL has an existing JSONL request protocol and capability discovery. The handoff's health/discovery adapter passed against its real source snapshot.
6. RIVET supplies useful command/presentation principles, but its reviewed UI contract is narrower than a full dashboard widget toolkit.
7. MACH is a Phase 0 typed agent runtime prototype, not an inference engine.

See immutable source links and `evidence/sources.json`; recheck upstream before making claims about later versions.

## What is actually implemented

The package runs with standard-library Python. It contains a shared action registry, scalar validation, CLI, curses TUI, local web UI, process jobs, cancellation, timeouts, bounded output, saved JSON records, explicit connection availability, browser presets, a QEC argparse bridge, CONTROL health/discovery and a local Ollama streaming adapter.

The Rust/Ratatui production route remains a decision to evaluate. No Rust workbench was built in this handoff. The Python baseline makes the protocol and integration behavior executable now; it is not evidence that Python outperforms another stack.

## Verification and boundaries

Run `python3 -m unittest discover -s tests -v`, `python3 workbench.py discover`, and the documented demo. Local sockets are needed for two HTTP tests. Browser evidence includes real headless Chrome form execution and cancellation. TUI evidence includes an interactive PTY demo run.

The QEC argument-refresh test uses a temporary QEC-shaped fixture, not a complete scientific installation. The Ollama test uses a local HTTP fixture, not loaded model weights. Read `docs/VALIDATION.md` before saying those integrations are fully validated.

Records are ordinary local observations with integrity checksums. Do not equate them with signed PROVENANCE records, scientific correctness, exact replay, authority, or deterministic model output. Do not change a failure into success or substitute demo data for unavailable live data.

## Suggested next work

1. Review the code for correctness and the contract for unnecessary complexity.
2. Prepare or connect a real QEC environment and complete P1's benchmark-to-manifest check.
3. Add a backend-owned capability export so production discovery need not depend on argparse internals.
4. Add one more genuine QEC operation and a useful CONTROL read workflow through adapters.
5. Decide whether long-running jobs must survive frontend shutdown and whether Rust is required for distribution.

Keep QEC and other engines in their existing repositories. Changes to remote repositories, publishing and release management require the user's relevant authorization; none were performed for this bundle.

## When responding to Trent

Lead with concrete findings and completed work. Distinguish observed source behavior, tested behavior, engineering recommendations and future work. Avoid an unnecessary full rewrite, broad untested claims, or a roadmap presented as implemented software. The user values autonomous progress and a small maintainable design.
