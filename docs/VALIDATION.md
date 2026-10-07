# Validation evidence and limits

## Phase 0 repository validation

The seven initial PR findings were reproduced and fixed on 7 October 2026. The updated suite passes **34 Python tests and four Node frontend tests**. New tests exercise safe/unsafe browser integers and defaults/choices, fractional strings that round to integers, converted QEC defaults and an unpackaged checkout without PYTHONPATH, zero-exit protocol failures, lone-surrogate and injected serialization failures, nonzero CLI reporting, HTTP inspection, legacy TUI history rendering and shared cancellation of an Ollama worker blocked in HTTP. The frontend suite runs the full application script against DOM/HTTP fixtures in Node; it is not a replacement for full Chrome acceptance.

Python compilation, JavaScript syntax, the regenerated manifest and archive extraction/demo were rechecked after the fixes. Real QEC and real-model evidence boundaries remain unchanged. The initial import evidence below records the earlier 25-test baseline.

The repository import was validated on 7 October 2026 with Linux, Python 3.12.14 and Node 24.19.0. All **25 tests passed**, including five new saved-record regressions. Python compilation, both JavaScript syntax checks, CLI discovery/result 42, archive checksum, complete extracted manifest and extracted demo passed. Added-file and duplicate-entry probes confirm manifest verification fails for incomplete coverage or repeated entries.

New coverage rejects modified results/inputs, missing or malformed final checksums, malformed objects, unknown statuses and mismatched run identities. It checks verified interrupted views preserve the original stored object and bytes, legacy unfinished records are explicitly unverified, corrupt records are omitted from history, and CLI inspection returns an integrity error.

`.github/workflows/phase0.yml` runs Linux Python 3.10 and 3.14 checks; their results belong to GitHub Actions rather than this local Python 3.12 run. Browser/TUI acceptance and the real CONTROL record below are preserved original handoff evidence. They were not rerun during the repository import. No Chrome/Chromium executable was available in this workspace. Real QEC scientific execution and real-model generation remain unvalidated gates.

The remaining sections describe Astra's original handoff validation. Original evidence files were preserved without changing their contents.

## Original handoff environment

Validation date: **7 October 2026**. Host: Linux, Python **3.14.4**, Node **22.18.0**. The package declares Python 3.10+, but other Python versions and operating systems were not exercised in this session.

## Automated behavior tests

Command: `python3 -m unittest discover -s tests -v`

**Result: 20 tests passed.** The exact transcript is `evidence/unit-tests.txt`.

The suite covers:

- Strict types, numeric bounds, choices and defaults.
- Rejection of unknown fields, duplicate JSON members and non-finite values.
- CONTROL error envelopes and mismatched response correlation.
- Literal argument transport without shell evaluation.
- Nonzero exit status and preserved stderr.
- Output caps, deadlines, cancellation and POSIX descendant cleanup.
- Explicit unavailable backends; no automatic demo fallback.
- Invalid JSON result handling.
- Simultaneous job limits and refresh refusal during active work.
- Persisted results and recomputed record checksums.
- Rejection of stale capability fingerprints and invalid run IDs.
- QEC-shaped parser changes that introduce a new argument, followed by refresh, successful execution and receipt of the new value.
- CONTROL JSONL request/response behavior using a fixture process.
- Ollama discovery and streamed generation using a local HTTP fixture.
- Authenticated local HTTP execution, with wrong token/Origin/Host rejection.

The first attempt under a restricted sandbox passed non-network tests but could not create loopback sockets for two HTTP tests. The final run used approved local-socket access and passed all 20. This was an environment permission limitation, not an ignored failing assertion.

## Browser acceptance

The actual browser interface was exercised in headless Google Chrome using Node's native WebSocket support and the Chrome DevTools Protocol. No Playwright/Puppeteer dependency was required.

`tools/browser_smoke.mjs` checked that:

1. The page loads and creates the demo form from the manifest.
2. Submitting steps=3, seed=7 and delay=0 produces total=42.
3. The inspector updates to a successful run through polling.
4. A longer second run can be cancelled from the UI.
5. No uncaught browser runtime exceptions occur during those checks.

The evidence is in `evidence/browser-tests.json` and `evidence/browser.png`. The screenshot was visually inspected for layout/readability. A history-refresh issue noticed during the first screenshot inspection was corrected and the browser acceptance check repeated successfully.

This does not establish full accessibility conformance, all mobile layouts, browser engine parity, or real-model inference UX. Those remain future checks.

## Interactive terminal check

The curses interface was launched in a real PTY using `TERM=xterm-256color`. The demo action was started with `r`, progress appeared, status reached `succeeded`, the result was displayed, and `q` restored the terminal. The produced run record is `evidence/tui-demo-run.json`.

This is a functional smoke check, not an exhaustive terminal emulator, resize, Unicode-width or keyboard-layout matrix. Very small terminals and long-field editing remain limited.

## Real CONTROL source check

The public CONTROL source was downloaded at commit:

```text
55c3fbee6435d4a6206aa946579f36724698a20b
```

Its actual `tools/agent_api.py` entry point ran locally with a fresh temporary storage root. The workbench sent a genuine `control.capabilities` request during discovery, then executed `control.health` through the same adapter. Both returned successful protocol envelopes. The final health response indicated available/valid CONTROL storage and unconfigured NEXUS/ORACLE parents.

The original run record is `evidence/control-live-run.json`. Its absolute `/tmp` paths describe this validation environment; they are not paths to copy into a user's configuration. No CONTROL repository source was modified. This check does not validate the optional remote gateway, council operations, replay execution, external parent services or mutations.

## QEC adapter boundary

The real reviewed QEC CLI parser defines the command shape used by the adapter. Tests create an isolated importable fixture with the same parser entry-point pattern, add a new scalar option, refresh discovery and prove that the new value reaches execution without UI changes.

**No full QEC scientific environment or real ququart benchmark run was executed here.** The next acceptance gate is P1 in `IMPLEMENTATION_PLAN.md`. The missing historical TUI adapter modules remain outside this implementation.

## Inference boundary

The implementation follows Ollama's documented `/api/tags` and `/api/generate` endpoints. Tests use a local server fixture returning model metadata and two valid streamed response events.

**No actual Ollama installation or model weights were used.** Model loading, hardware behavior, provider cancellation and inference timing are unverified. The application records a seed but does not claim deterministic model output.

## Additional checks

- Python sources were compiled/parsed successfully.
- Browser JavaScript passed `node --check`.
- The CLI demo produced the known result 42; `evidence/demo-run.json` retains that record.
- Source provenance is recorded in `evidence/sources.json` without bundling external codebases.

The archive build writes an internal per-file manifest and an external `.zip256` checksum. Final packaging verification is performed separately against the built archive, including extraction and a demo run from that extracted tree. A checksum establishes byte integrity, not author identity or behavioral correctness.

## Known implementation limits

- Single-user local service; no remote hosting or cross-process job coordination.
- Per-session memory retains completed run records; a long-lived retention design is pending.
- Intermediate output is not durably journaled; final records are atomically written.
- Backend identities are informative snapshots, not complete reproducible environment locks.
- The QEC bridge uses argparse internals and a limited scalar subset.
- CONTROL exposes only health/capabilities and starts one process per request.
- The AI module is single-prompt streaming, not an advanced multi-turn assistant.
- Generic arbitrary stdin event-stream viewing is planned; this version accepts JSON parameters from stdin and captures adapter output.
- Browser embedding, RIVET presentation, PROVENANCE and MACH integrations are not implemented.
- No performance benchmark, package-install test, Windows support claim or multi-Python CI matrix is supplied.

These limits should remain visible in future handoffs until appropriate evidence supersedes them.
