# WORKBENCH roadmap

The detailed work and acceptance contracts live in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). A phase completes when its evidence gate passes. Shipped capabilities, tested environments and future work are kept distinct.

| Phase | Outcome | Status | Acceptance gate |
|---|---|---|---|
| P0 | Shared reference runtime, CLI/TUI/web and adapters | Merged | Demo, behavior tests, records and bundle verification |
| P1 | First supported real QEC environment | Merged; real acceptance passed | Direct, CLI and browser runs produce validated equivalent QEC artifacts |
| P2 | Backend-owned capability descriptors | Implemented; real three-operation parity passed | Typed backend exports replace argparse internals; refresh and stale-schema handling retain execution parity |
| P3 | Useful independent CONTROL read workflow | Planned | Add an operation through its adapter and tests while retaining response correlation and provenance |
| P4 | Production runtime/presentation decision | Planned after P1–P3 | Measure resource use, responsiveness and installation; demonstrate parity before migration |
| P5 | Durable lifecycle and artifact inspection | Planned | Distinct failures, bounded history, explicit recovery and artifact export |
| P6 | Release, installation and migration | Planned | Install a release artifact on a clean machine; exercise update and rollback |
| P7 | Optional AI workspace expansion | Planned | Validate a real model, then add workflow-driven capabilities with accurate provider semantics |
| P8 | Optional ecosystem integrations | Planned | Independent value/evidence gates for PROVENANCE, Browsh, RIVET and MACH |

## P1 evidence

[QEC acceptance instructions](QEC_ACCEPTANCE.md) describe the pinned environment, commands and verifier. [Retained evidence](../evidence/p1-qec/summary.json) records the real gate: QEC commit `7103836d731a869dc82b077bc0b920a76072f08e`, package 173.0.0, clean CPython 3.12.14 venv on Linux x86_64, NumPy 2.3.5 and SciPy 1.17.0.

The small workload uses two error rates, 40 Monte Carlo trials per cell, 30 harmonic trials per cell and seed 31. Each interface writes to its own new output directory. All 15 files per successful run match byte for byte; QEC's own validator accepts all three reports. Zero-trial failures and an invalid threshold claim remain inspectable evidence. These counts prove integration and do not establish a new scientific claim.

P1 also fixes virtual-environment interpreter selection: resolving a Python executable symlink selected the base interpreter and hid the installed QEC package. The adapter now normalizes the configured path while preserving that symlink.

## P2 evidence

[Descriptor setup and acceptance](QEC_DESCRIPTORS.md) documents the QEC companion and native/legacy compatibility. [Retained evidence](../evidence/p2-qec/summary.json) pins the companion source and proves byte-identical direct/CLI/Chromium output for ququart benchmark (15 artifacts), qutrit benchmark (13 artifacts), and ququart report validation. Backend exports and public parsers share scalar declarations; discovery does not import scientific command modules. Refresh, stale-schema rejection and unsupported-input failures have separate fixture proofs.

## Next: P3

Add one useful existing CONTROL read workflow through its adapter, preserve response correlation and provenance, and prove it in CLI/browser without adding backend dispatch to the frontend. Inspect CONTROL's actual schemas before choosing the operation.

Real-model inference, unfinished QEC diagnostics/history panels, production packaging, background jobs and cross-process coordination retain their existing gates. Optional integrations do not become base dependencies merely by appearing here.
