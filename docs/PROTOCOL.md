# Workbench protocol and extension contract

## Version and scope

`qsol-workbench/1` identifies this prototype's capability manifest. `qsol-workbench-run/1` identifies its run records. These are local reference contracts, not established ecosystem standards. The implementation supports a limited scalar form vocabulary; it does not implement arbitrary JSON Schema, OpenAPI, RPC or downloadable plugins.

The canonical domain path is:

```text
adapter discovery -> Action -> field validation -> Plan -> bounded execution -> run record
```

CLI, curses and HTTP clients all use `Runtime`. They do not construct backend commands independently.

## Manifest

`Runtime.manifest()` / `GET /api/manifest` returns:

```json
{
  "protocol": "qsol-workbench/1",
  "workbench_version": "0.1.0",
  "store": "/operator/selected/run/store",
  "connections": [{"id":"demo","status":"available","actions":["demo.experiment"]}],
  "actions": [{
    "id":"demo.experiment",
    "title":"Demo experiment",
    "description":"Explicitly labelled sample computation",
    "fields":[{"name":"steps","type":"integer","label":"Steps","default":5,"minimum":1,"maximum":100}],
    "backend":{"kind":"demo","version":"1"},
    "effect":"local-compute",
    "schema_sha256":"sha256-of-the-complete-public-action-object-without-this-field"
  }]
}
```

This example is abbreviated. Available connections list supported action IDs. Disabled connections have no actions. Unavailable connections contain a reason and publish no executable actions. Error text comes from the configured local adapter; frontends display it as text.

## Input vocabulary

Each field requires `name`, `type` and a display `label`. Supported types are `string`, `integer`, `number`, and `boolean`.

Optional properties:

- `default`: materialized by the core when the caller omits a value.
- `required`: omission without a default is rejected; required strings cannot be empty.
- `choices`: explicit allowed values.
- `minimum` / `maximum`: inclusive bounds for numeric inputs.
- `max_length`: string character limit (default 32768).
- `multiline`: browser presentation hint.
- `help`: human-readable explanation.
- `flag`: QEC adapter's declared option spelling; clients do not build argv from it.
- `path_role` / `path_base`: native QEC path semantics; strings are passed unchanged and relative paths use backend cwd.

Unknown input names, type mismatches, integer/bool aliases, non-finite numbers, duplicate JSON members and invalid choices are rejected. The core validates defaults as well as submitted values. These checks do not replace backend scientific validation. A string such as QEC's comma-separated error-rate list retains its backend-defined grammar.

The browser accepts whole decimal integer text only within JavaScript's exact safe range, −9007199254740991 through 9007199254740991. It checks the text with `BigInt` before converting to a JSON number and rejects larger values before dispatch or preset save, including unsafe discovered defaults/choices. CLI/TUI and direct API callers can supply larger integers supported by the backend. Number fields retain floating-point semantics. Boolean choices use the selected option's JSON boolean value; unconstrained booleans use checkboxes. Defaults and browser presets restore the corresponding control value.

Native QEC discovery consumes `qec-capabilities/1` from the installed provider. Three reviewed entry points publish shared scalar declarations, including boolean values, path roles and versioned output contracts. Unsupported shapes/protocols fail explicitly. See [QEC descriptors](QEC_DESCRIPTORS.md).

Explicit `discovery: legacy-argparse` supports older backends. This legacy QEC bridge supports ordinary scalar argparse store actions with built-in string/int/float or `pathlib.Path` converters. Boolean argparse actions, positional arguments, lists, subparsers and custom converters currently require adapter work. The probe rejects unsupported shapes rather than presenting an incomplete form. It uses argparse's internal `_actions` interface as a temporary compatibility bridge; native discovery is the default, without automatic fallback.

String defaults pass through the declared converter, matching argparse behavior; non-string defaults remain unchanged, and Path defaults and choice members are exported as strings. When Python prepends an implicit import path, the isolated probe replaces its script directory with the configured working directory to match the eventual `python -m` invocation, including unpackaged checkouts. Under Python 3.11+ safe-path mode, the probe leaves the interpreter's import paths unchanged: it does not inject cwd or replace an explicit PYTHONPATH entry. A cwd-only backend is therefore unavailable when execution cannot import it; an explicitly configured import path remains usable.

QEC reports a distribution version only when that distribution's file inventory includes the imported provider module (CLI module in legacy mode). Same-named unrelated metadata is ignored. When ownership cannot be established, including editable installs without the source module in their inventory, the identity is `unpackaged-checkout` alongside the actual module path and hash. This association is not an authenticated provenance check.

## Capability identity and refresh

`schema_sha256` hashes the public action description, including fields and advertised backend identity, using sorted-key compact UTF-8 JSON. It is not a signed identity or a complete backend environment fingerprint.

The browser submits that hash with each action request. The core rejects a differing fingerprint. Refresh rediscovers enabled adapters and reconstructs forms. Refresh is refused while jobs are active. Discovery does not automatically run continuously; changing the environment requires refresh or restart. External changes after discovery remain possible, so production integration should bind a descriptor to an immutable backend instance or revalidate before dispatch.

## Execution plan

An internal `Plan` contains:

```text
argv                  string array, passed directly to subprocess.Popen
cwd                   optional explicit working directory
stdin                 optional UTF-8 payload, written by the transport
result_kind           json | control | ollama
expected_operation    optional CONTROL response correlation check
expected_schema       optional JSON result schema check
success_field         optional JSON field required to be true
```

There is no shell evaluation. The HTTP API cannot submit an arbitrary argv or rewrite adapter configuration. Configuration is loaded from an operator-selected local file. That file is trusted and can deliberately invoke local programs.

The QEC adapter preserves the configured interpreter symlink so a virtual environment retains its installed packages; it normalizes relative path components without selecting the base interpreter.

QEC starts the selected interpreter with `-m` and the adapter-reviewed ququart benchmark/validator or qutrit benchmark module. CONTROL receives one request line and an EOF. Ollama uses a worker process so HTTP transport can be interrupted through the same job-control interface.

Ollama generation has no independent socket timeout: the shared run deadline and cancellation terminate its worker, including a blocked connection or read. Model-list discovery retains its short probe deadline.

## Local HTTP API

The server accepts only its exact loopback Host value, and rejects a supplied mismatched Origin. API requests need `Authorization: Bearer <session-token>`. Authentication and GET/POST routing share the URL-split request path, so absolute-form and origin-form API targets require the same token. Malformed targets are rejected. Mutating requests require a JSON body with a bounded explicit Content-Length. There is no CORS allowance, remote binding option or endpoint to change configuration.

| Method | Path | Meaning |
|---|---|---|
| GET | `/api/manifest` | Current capability snapshot |
| GET | `/api/runs` | Latest 100 run summaries |
| GET | `/api/runs/<id>` | Current or saved record |
| POST | `/api/run` | `{action, parameters, schema_sha256}`; returns a queued record |
| POST | `/api/cancel` | `{id}`; requests cancellation of an owned job |
| POST | `/api/refresh` | `{}`; rediscovers configured adapters |

`schema_sha256` is optional for raw callers, while the bundled browser sends it. Server-side input validation applies either way. Error responses contain an `error` string. Job failures are run outcomes, not necessarily HTTP failures.

## Job states and records

```text
queued -> running -> succeeded | failed | cancelled | timed_out | output_limit
saved unfinished record loaded by a new process -> interrupted (view classification)
```

Record content includes action ID, full capability snapshot, normalized parameters, backend identity, argv/cwd, creation/start/finish times, captured stdout/stderr, exit code when available, parsed result and error. A successful OS process with invalid required JSON is classified as failed. CONTROL error envelopes cannot become success merely because the process exited zero. An Ollama stream must contain a terminal completion event. Native QEC results must match their declared schema; validation receipts require `passed: true`. Optional public `output` metadata drives generic browser artifact-manifest and validation-receipt views. These views display backend-reported content as text.

Transport fields are retained before interpreting output. `transport_status` records the executor outcome separately from the final run `status`; a zero-exit malformed JSON, CONTROL or Ollama response retains `exit_code: 0`, captured output and `transport_status: succeeded`, while the final run is `failed`. The run stays active until interpretation finishes.

During a run, output is kept in memory and exposed through polling. A queued record is persisted before execution, then atomically replaced with the final record. This is not a durable event stream: intermediate output can be lost on abrupt application death. The last unfinished disk record is reported as interrupted on a new process's read, without claiming the backend was rolled back.

Each saved `record_sha256` is computed before adding that field. Remove it before recomputation. On disk reads, the runtime validates the object, protocol, run identity and known status, then verifies the checksum before interpreting the record. Final records require a checksum; malformed or mismatched checksums are rejected. History omits invalid records; direct CLI/API inspection reports the error. Owned jobs are read from session memory and do not trigger disk verification.

For unfinished records, the returned view uses `status: interrupted`, an explanatory error, and no top-level `record_sha256`. `stored_record` contains the exact parsed disk object and `stored_record_integrity` is `verified` when its checksum passed. Legacy unfinished records with no checksum are explicitly `unverified`. No inspection rewrites the stored file. A checksum validates content consistency, not authenticity; replacing both content and checksum cannot be detected by this local format.

A persistence error is reported in the in-memory record and yields a nonzero CLI run outcome; it is not concealed as successfully saved evidence. There is no automatic signature, trusted timestamp or exact-replay guarantee.

Final persistence catches JSON serialization, Unicode encoding and filesystem failures. An unsaved in-memory final record has `persistence_error` and no `record_sha256`; it is not rehashed after a serialization failure. CLI/HTTP JSON presentation escapes Unicode so such failures remain inspectable, including parsed lone surrogates. The previous disk snapshot remains the recovery record. Browser and TUI history tolerate missing legacy output fields and display persistence errors.

## Extending the implementation

1. Add a factory to the explicit built-in adapter registry.
2. Discover the backend in its own environment and report failures as unavailable.
3. Return `Action` objects with typed fields and a `build` function.
4. Produce an execution plan using a fixed reviewed entry point and validated values.
5. Add a contract fixture and, where possible, a real-backend smoke test.
6. Demonstrate the new operation through CLI and browser without adding backend-specific branches to either frontend.

Do not copy a backend's full business logic into its adapter. For richer data, evolve a versioned field/result contract with tests before adding bespoke UI branches. The next production iteration should separate transport/job events from large artifact storage and adopt explicit adapter/protocol version negotiation.
