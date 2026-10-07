# Changelog

## Phase 0 repository baseline — 2026-10-07

Review fixes:

- Authenticate normalized absolute-form API targets and share the same path with GET/POST routing.
- Serialize QEC Path choices and bind advertised versions to metadata owning the imported CLI module.
- Render legacy inference history without stdout; submit and restore boolean select values correctly.
- Expand current regression coverage to 38 Python tests and seven Node frontend tests.

- Respect Python safe-path mode in QEC discovery; test normal cwd imports, rejected implicit cwd imports and preserved explicit PYTHONPATH against direct execution.

- Reject unsafe browser integer values before dispatch, with decimal-text validation and four frontend regression tests.
- Match argparse conversion of string defaults and align QEC probe imports with execution from unpackaged checkouts.
- Classify final serialization/encoding errors as persistence failures; retain inspectable JSON and avoid rehashing unsaved records.
- Preserve transport status, exit code and captured output before interpreting backend responses.
- Let the shared runtime enforce Ollama generation deadlines, including blocked sockets.
- Render legacy TUI records without requiring stdout/stderr and show persistence errors.
- Expand Python coverage from 25 to 34 tests and add browser regression checks to CI.

Initial import:

- Imported Astra's 0.1.0 reference implementation and preserved the original evidence and handoff manifest.
- Organized usage, report and historical handoff documentation; added concise repository entry points.
- Adopted the existing Apache-2.0 repository license and `qsol-workbench` package identity.
- Added Linux CI for Python 3.10/3.14, JavaScript syntax, CLI discovery/demo and deterministic archive verification.
- Added automatic disk-record checksum validation, checksums for queued snapshots and explicit stored-record/interrupted-view separation.
- Added regression coverage for changed, malformed, misidentified and legacy unfinished records.
- Required complete manifest coverage, including the historical manifest.

The package remains version 0.1.0; this import does not publish a release or satisfy the real-QEC P1 gate.

## 0.1.0 — 2026-10-07

- Added source-backed architecture report and project-specific migration plan.
- Implemented shared capability/validation/execution core with CLI, curses and local web presentations.
- Added an explicit demo, QEC parser bridge, CONTROL read operations, and optional local Ollama streaming.
- Added bounded subprocess execution, cancellation, deadlines, saved run records and checksums.
- Added 20 behavior tests, browser acceptance automation, and real CONTROL smoke evidence.
- Packaged source, documentation and evidence with internal/external SHA-256 manifests.

This is a reference prototype. Production release infrastructure and the broader optional modules remain planned.
