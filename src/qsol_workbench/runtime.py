"""Shared registry, bounded jobs, and persistent local run records."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
import uuid

from . import __version__
from .adapters.builtin import check_control, discover
from .model import digest, json_loads, validate
from .process import execute

ACTIVE = {"queued", "running"}
FINAL = {"succeeded", "failed", "cancelled", "timed_out", "output_limit"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Runtime:
    def __init__(self, config=None, store=".workbench/runs", timeout=120):
        self.config = deepcopy(config or {})
        self.store = Path(store).expanduser().resolve()
        self.store.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.lock = threading.RLock()
        self.jobs = {}
        self.actions, self.connections = discover(self.config)

    def manifest(self):
        with self.lock:
            return {"protocol": "qsol-workbench/1", "workbench_version": __version__,
                    "store": str(self.store), "connections": deepcopy(self.connections),
                    "actions": [a.public() for a in self.actions.values()]}

    def refresh(self):
        with self.lock:
            if any(j["record"]["status"] in ACTIVE for j in self.jobs.values()):
                raise ValueError("Wait for active jobs before refreshing connections")
            self.actions, self.connections = discover(self.config)
            return self.manifest()

    def start(self, action_id, supplied, schema_sha256=None):
        with self.lock:
            if action_id not in self.actions:
                raise ValueError("Action is unavailable or unknown")
            if sum(j["record"]["status"] in ACTIVE for j in self.jobs.values()) >= 4:
                raise ValueError("At most four simultaneous jobs are supported")
            action = self.actions[action_id]
            spec = action.public()
            if schema_sha256 is not None and schema_sha256 != spec["schema_sha256"]:
                raise ValueError("Capability schema changed; refresh the form before running")
            params = validate(action.fields, supplied)
            plan = action.build(params)
            run_id = uuid.uuid4().hex
            record = {"protocol": "qsol-workbench-run/1", "id": run_id,
                      "workbench_version": __version__, "action": action_id,
                      "capability": spec, "parameters": params, "status": "queued",
                      "created_at": now(), "execution": {"argv": plan.argv, "cwd": plan.cwd},
                      "stdout": "", "stderr": "", "result": None, "error": None}
            job = {"record": record, "cancel": threading.Event()}
            # Fail before execution if records cannot be persisted.
            self._save(record)
            self.jobs[run_id] = job
            worker = threading.Thread(target=self._run, args=(job, plan), daemon=True)
            job["thread"] = worker
            worker.start()
            return deepcopy(record)

    def _save(self, record):
        record.pop("record_sha256", None)
        record["record_sha256"] = digest(record)
        path = self.store / (record["id"] + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                             encoding="utf-8")
        temporary.replace(path)

    def _run(self, job, plan):
        record = job["record"]
        with self.lock:
            record.pop("record_sha256", None)
            record.update(status="running", started_at=now())

        def emit(name, text):
            with self.lock:
                record[name] += text

        try:
            result = execute(plan, cancel=job["cancel"], emit=emit, timeout=self.timeout)
            with self.lock:
                record.update({key: value for key, value in result.items() if key != "status"})
                record["transport_status"] = result["status"]
            parsed = None
            if result["status"] == "succeeded":
                if plan.result_kind == "ollama":
                    events = [json_loads(line) for line in result["stdout"].splitlines() if line.strip()]
                    if not events or events[-1].get("done") is not True:
                        raise ValueError("Inference has no completed result")
                    parsed = {"text": "".join(e.get("response", "") for e in events),
                              "completion": events[-1]}
                else:
                    parsed = json_loads(result["stdout"])
                    if plan.result_kind == "control":
                        check_control(parsed, plan.expected_operation)
                if plan.expected_schema is not None and (not isinstance(parsed, dict) or parsed.get("schema") != plan.expected_schema):
                    raise ValueError("Backend result does not match the declared output schema")
                if plan.success_field is not None and parsed.get(plan.success_field) is not True:
                    raise ValueError("Backend result does not report successful validation")
                if plan.validate_result is not None:
                    plan.validate_result(parsed)
            with self.lock:
                record.update(status=result["status"], result=parsed)
        except Exception as error:
            with self.lock:
                record.update(status="failed", error=f"{type(error).__name__}: {error}")
        finally:
            with self.lock:
                record["finished_at"] = now()
                try:
                    self._save(record)
                except (OSError, ValueError, TypeError) as error:
                    # UnicodeError is a ValueError. Do not rehash a record that
                    # may itself have failed JSON serialization or UTF-8 encoding.
                    record["persistence_error"] = f"{type(error).__name__}: {error}"
                    record.pop("record_sha256", None)

    def get(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid run ID")
        with self.lock:
            if run_id in self.jobs:
                return deepcopy(self.jobs[run_id]["record"])
        path = self.store / (run_id + ".json")
        record = json_loads(path.read_text(encoding="utf-8"))
        if (not isinstance(record, dict)
                or record.get("protocol") != "qsol-workbench-run/1"
                or record.get("id") != run_id
                or not isinstance(record.get("status"), str)
                or record["status"] not in ACTIVE | FINAL):
            raise ValueError("Invalid stored run record")
        stored = deepcopy(record)
        checksum = record.pop("record_sha256", None)
        if "record_sha256" in stored:
            if (not isinstance(checksum, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", checksum)
                    or checksum != digest(record)):
                raise ValueError("Run record checksum mismatch")
        elif record["status"] in FINAL:
            raise ValueError("Final run record is missing its checksum")
        if record["status"] in ACTIVE:
            record["status"] = "interrupted"
            record["error"] = "Owner process ended before a final run record was saved"
            # The interpreted view has no checksum. Preserve the exact stored
            # object separately, including its original checksum when present.
            record["stored_record"] = stored
            record["stored_record_integrity"] = "verified" if checksum else "unverified"
            return record
        return stored

    def history(self):
        # Load only the most recent 100; avoid pulling every run's large output.
        paths = sorted(self.store.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        result = []
        for path in paths:
            try:
                record = self.get(path.stem)
                result.append({k: record.get(k) for k in ("id", "action", "status", "created_at")})
            except (ValueError, OSError, KeyError):
                continue
        return result

    def cancel(self, run_id):
        with self.lock:
            if run_id not in self.jobs:
                raise ValueError("Only a job owned by this process can be cancelled")
            self.jobs[run_id]["cancel"].set()
            return self.get(run_id)

    def wait(self, run_id):
        with self.lock:
            thread = self.jobs[run_id]["thread"]
        thread.join()
        return self.get(run_id)

    def close(self):
        with self.lock:
            jobs = list(self.jobs.values())
            for job in jobs:
                job["cancel"].set()
        for job in jobs:
            job["thread"].join(timeout=10)
