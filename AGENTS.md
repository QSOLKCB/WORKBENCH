# Working on WORKBENCH

Read `README.md`, `GETTING_STARTED.md`, `docs/PROTOCOL.md` and `docs/VALIDATION.md` first.
Historical handoff material lives in `docs/handoff/`; current usage is in `docs/USAGE.md`.

- Preserve one shared validation/execution path for CLI, TUI and web.
- Keep backend semantics inside the backend or its explicit adapter.
- Do not substitute demo data for failed live operations.
- Use argument arrays; do not introduce shell evaluation of UI values.
- Keep optional backend dependencies outside the base runtime.
- Treat the current bundle as a reference prototype; preserve its documented limitations until tests justify changing them.
- Add behavior tests for new adapter contracts and failure modes.
- Record which tests use fixtures versus real backend installations.
- Do not publish new upstream releases or modify remote repositories without relevant user authorization.
- Regenerate the bundle manifest and checksum after changing bundled files.
- Run `python3 -m unittest discover -s tests -v`, Python compilation, JavaScript syntax checks and manifest verification before proposing a merge.

This file does not request sub-agents or parallel delegation.
