# Implementation plan and migration gates

This is an executable-work plan, not a promise that all listed work has shipped. P0 is the bundled reference baseline. Subsequent phases need their stated acceptance evidence before completion claims.

## P0 — Reviewable reference baseline (delivered)

**Outcome:** Demonstrate the architecture with actual code and clear boundaries.

Delivered: capability registry, scalar validation, CLI, curses presentation, local web UI, job lifecycle, bounded output, local records, QEC parser bridge, CONTROL health/discovery, local Ollama transport, tests, browser acceptance script and full report.

Repository baseline additions: Apache-2.0 licensing, `qsol-workbench` package identity, organized handoff documentation, Linux CI, verified disk records, explicit interrupted views and complete manifest/archive verification. The package remains 0.1.0; no release has been published by this import.

**Gate:** Run the demo, verify the known result 42, pass tests, inspect the real CONTROL evidence, and verify the ZIP/checksum. See `VALIDATION.md` for exact evidence; do not infer real QEC scientific execution or real model generation from fixture tests.

## P1 — Establish the first supported QEC environment

**Work:**

1. Record the intended OS, architecture, interpreter and QEC source/release identity.
2. Prepare QEC using its own current installation instructions in a separate environment.
3. Run the benchmark directly with a small explicit input and a new output directory.
4. Connect that same interpreter and working directory to the workbench.
5. Run the identical inputs through CLI and web forms into separate directories.
6. Compare the scientific manifest content under QEC's own validation rules. Separate path/timestamp differences from meaningful data differences.
7. Retain failing as well as successful outputs, and document required optional dependencies.

**Gate:** At least one real scientific workflow completes through the adapter, the expected artifacts exist, and QEC validates the result. Tiny trial counts demonstrate integration only; scientific claims need appropriate experimental runs.

**Do not:** Fill missing diagnostics/history/law modules with plausible sample data or invent their scientific semantics. The workbench can expose them only after QEC provides implemented operations and their own validation.

## P2 — Replace fragile discovery with backend-owned descriptors

The argparse probe proves the concept, but `_actions` is an internal interface and imports can have startup costs/side effects. Add an explicit export path in QEC, preferably generated from the same typed command declarations that construct its parser.

**Work:**

- Define descriptor protocol, action ID, input types, effects, output types and protocol compatibility.
- Export operation metadata from the installed backend instance.
- Preserve defaults, requiredness, choices, path semantics and meaningful bounds.
- Report unsupported/custom input structures explicitly.
- Add the next two existing QEC operations, selected by actual operator demand.
- Provide generic forms plus a custom artifact/report view when the result shape warrants it.

**Gate:** A backend change adding a supported option updates both interfaces after refresh. A stale schema submission is rejected. Direct CLI and workbench invocations use equivalent parameters. A new unsupported input type produces a clear compatibility error.

**Candidate workflow expansion:** ququart report validation, qutrit battery, or an existing routing demonstration. Inspect each actual CLI before selecting it; do not assume identical output formats.

## P3 — Prove reuse through CONTROL

The reference health/discovery integration already exercises a second project. Extend it with one useful read workflow, such as retrieving or comparing existing runs.

**Work:**

- Use CONTROL's existing request/response schemas and parameter validation.
- Map stable run identifiers into a typed workbench form.
- Render actual CONTROL records and preserve their provenance references.
- Decide whether a persistent stdio session is needed; the current one-request process lifecycle is deliberately limited.
- Revisit quotas and state isolation before exposing mutations or multiple users.

**Gate:** Add the operation using adapter and tests only; no core/frontend backend-specific dispatch. Responses remain correlated to the originating request and operation. Existing CONTROL boundaries are preserved.

## P4 — Production implementation decision

Choose among retaining the Python runtime, moving the terminal presentation to Rust/Ratatui, or migrating more of the core to Rust. Do this after P1–P3 reveal actual integration needs.

**Measure:** cold start, idle resident memory, response to long streamed logs, UI responsiveness during work, package size, installation steps, and maintenance complexity. Use the same action corpus and data limits for each candidate. Document measurements instead of claiming a language is inherently sufficient.

If Rust is chosen:

1. Freeze protocol fixtures and semantic tests.
2. Implement a client or runtime against them.
3. Keep Python/QEC behind a process boundary.
4. Port one workflow end to end before moving the rest.
5. Preserve backend identity and failure semantics.

**Gate:** The chosen stack runs QEC and CONTROL workflows with the same externally visible semantics, acceptable measured resource use, and a maintainable installation story. The current Python prototype remains a reference until parity is demonstrated.

## P5 — Reliable lifecycle, records and artifact inspection

**Work:**

- Decide whether jobs must outlive UI exit. If yes, introduce a separately supervised local runner with reconnect and explicit ownership.
- Persist bounded events or stream logs to disk so interrupted jobs retain evidence.
- Bound in-memory history and implement a user-visible disk retention policy.
- Add artifact references, file size/hash metadata and a safe explicit export path.
- Separate a replay comparison from rerunning a command; record relevant backend/environment differences.
- Improve TUI long-text editing, scrolling, terminal resize handling and keyboard discoverability.
- Add browser accessibility and mobile viewport checks.

**Gate:** A backend crash, frontend disconnect, full disk, malformed stream, timeout and user cancellation all produce distinct, inspectable outcomes. Recovery does not silently rerun a mutating action. Memory remains bounded under a sustained workload.

## P6 — Release, installation and migration

**Work:**

- Give workbench releases their own version and immutable build identity.
- Publish supported backend/protocol ranges and the exact tested matrix.
- Build platform artifacts and hashes from the release commit.
- Verify the uploaded installation artifact in a clean environment, not only the source tree.
- Add a `doctor` command reporting resolved paths, interpreter, backend version/source origin, supported actions and incompatibilities.
- Make release/development channels explicit.

**Migration:** Install the workbench alongside QEC's existing TUI. Migrate one useful workflow at a time. Keep a direct CLI escape hatch. Deprecate an old panel only after the replacement operates on real data and its acceptance tests pass. Do not publish a compatibility claim merely because both programs display the same release number.

**Gate:** A clean machine can install the selected artifact, run noninteractive probes, discover a supported backend and execute a sample. Missing assets or mismatched environments produce actionable errors. An update and rollback procedure has been exercised.

## P7 — Expand the optional AI workspace

The delivered Ollama module is a prompt playground. Choose the next capability from an actual user workflow rather than adding every possible AI feature.

Suggested sequence:

1. Validate against an installed real model and retain provider/version/model identity.
2. Add conversations with explicit message history and storage ownership.
3. Add side-by-side prompt/preset comparisons and useful timing/token observations.
4. Add another provider through a shared provider capability contract.
5. Add files, retrieval or tools only with explicit data ownership and execution boundaries.

**Gate:** Available controls match the connected provider's supported features; unsupported options cannot be silently accepted. Interrupted/error streams are distinct from completed model responses. Secret configuration is separated from exported experiment records. Provider cancellation semantics are documented and tested where supported.

Model downloading, training and a bundled inference engine are separate scope decisions. MACH can later provide typed agent execution when its required transport boundaries exist; do not treat its Phase 0 kernel as a model server.

## P8 — Optional extensions with explicit value tests

| Extension | First useful experiment | Gate before making it a dependency |
|---|---|---|
| PROVENANCE | Export one successful and one failed workbench run into its evidence model | Independent validation preserves observation/failure distinctions |
| Browsh viewer | Open one essential existing web dashboard from the terminal | Keyboard/focus/session behavior works and overhead is justified |
| RIVET presentation | Render the same discovered action and result through a native surface | Required forms, input, text and navigation meet operator needs |
| MACH executor | Dispatch one reviewed typed action and retain its receipt | No duplicated project semantics; clear outcome and trajectory boundaries |

These are optional modules. Their absence must not break the base demo/QEC/CONTROL installation.

## Definition of done for the first usable release

- Real QEC workflow and independent CONTROL workflow are usable.
- Scalar backend changes propagate without frontend edits.
- Connection identity and unavailable states are accurate.
- CLI/TUI/web behavior agrees on validated parameters and job outcomes.
- Release artifacts are tested through installation.
- Limits, storage, cancellation and recovery behavior are documented.
- The build/test evidence is attached to the actual release commit.
- The supported feature list distinguishes shipped code from roadmap items.

Broader framework functionality, additional protocols and external plugin distribution are separate release goals.
