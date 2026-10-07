import json
from pathlib import Path
import sys

from ..model import Action, Plan, field, json_loads
from ..process import execute
from ..worker import local_endpoint

WORKER = str(Path(__file__).resolve().parents[1] / "worker.py")


def probe(plan):
    result = execute(plan, timeout=12, max_output=256 * 1024)
    if result["status"] != "succeeded":
        raise ValueError((result["stderr"] or result["status"])[-2000:])
    return json_loads(result["stdout"])


def demo():
    fields = [field("label", default="First experiment"),
              field("steps", "integer", default=5, minimum=1, maximum=100),
              field("seed", "integer", default=7, minimum=0, maximum=1000000),
              field("delay", "number", default=.1, minimum=0, maximum=5)]
    return [Action("demo.experiment", "Demo experiment", "Deterministic sample with live progress; no QEC engine.",
                   fields, {"kind": "demo", "version": "1", "python": sys.executable},
                   lambda p: Plan([sys.executable, WORKER, "demo"], stdin=json.dumps(p)))]


def qec(config):
    python = str(Path(config["python"]).expanduser().resolve())
    cwd = str(Path(config.get("cwd", ".")).expanduser().resolve())
    discovery = probe(Plan([python, WORKER, "qec-probe"], cwd=cwd))
    fields = discovery["fields"]

    def build(params):
        argv = [python, "-m", "qec.benchmark.ququart_battery.cli"]
        for spec in fields:
            if spec["name"] in params:
                # --name=value preserves strings beginning with '-' as values.
                argv.append(spec["flag"] + "=" + str(params[spec["name"]]))
        return Plan(argv, cwd=cwd)

    return [Action("qec.ququart.benchmark", "QEC ququart evidence battery",
                   "Runs the installed QEC benchmark and returns its manifest. Writes to the selected output directory.",
                   fields, {**discovery["backend"], "cwd": cwd}, build, "writes-artifacts")]


def control(config):
    argv = config["argv"]
    if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
        raise ValueError("CONTROL argv must be a nonempty string array")
    cwd = str(Path(config.get("cwd", ".")).expanduser().resolve())

    def request(operation, params):
        payload = {"protocol": "qsol-control-agent-request/1", "request_id": "workbench-request",
                   "caller": {"kind": "human", "id": "qsol-workbench"},
                   "operation": operation, "params": params}
        return Plan(argv, cwd=cwd, stdin=json.dumps(payload) + "\n", result_kind="control", expected_operation=operation)

    response = probe(request("control.capabilities", {}))
    check_control(response, "control.capabilities")
    # Capability discovery is retained as evidence, not interpreted as permission
    # to expose every mutation. These two read operations are explicitly supported.
    identity = {"kind": "control", "protocol": "qsol-control-agent-api/1", "argv": argv,
                "cwd": cwd, "discovery": response}
    return [Action(operation, title, "Read-only CONTROL operation over JSONL/stdio.", [], identity,
                   lambda p, operation=operation: request(operation, p), "read")
            for operation, title in [("control.health", "CONTROL health"),
                                     ("control.capabilities", "CONTROL capabilities")]]


def check_control(response, operation=None):
    if not isinstance(response, dict):
        raise ValueError("CONTROL response must be an object")
    if response.get("protocol") != "qsol-control-agent-response/1":
        raise ValueError("CONTROL returned an error or an unsupported response protocol: " + json.dumps(response)[:1000])
    if response.get("request_id") != "workbench-request":
        raise ValueError("CONTROL response request_id mismatch")
    if response.get("ok") is not True or response.get("authority") != "orchestration-only" or "result" not in response:
        raise ValueError("Malformed CONTROL success response")
    if operation is not None and response.get("operation") != operation:
        raise ValueError("CONTROL response operation mismatch")
    return response


def ollama(config):
    url = local_endpoint(config.get("url", "http://127.0.0.1:11434"))
    models = probe(Plan([sys.executable, WORKER, "ollama-probe", url]))["models"]
    if not models:
        raise ValueError("Ollama has no installed models; install a model separately")
    fields = [field("model", choices=models, default=models[0], required=True),
              field("prompt", required=True, multiline=True, max_length=32768),
              field("temperature", "number", default=.7, minimum=0, maximum=2),
              field("seed", "integer", default=42, minimum=0, maximum=2147483647)]
    return [Action("inference.generate", "Local model playground", "Streams a prompt through an existing local Ollama server.",
                   fields, {"kind": "ollama", "url": url, "models": models},
                   lambda p: Plan([sys.executable, WORKER, "ollama-generate", url],
                                  stdin=json.dumps(p), result_kind="ollama"), "inference")]


def discover(config):
    actions, connections = {}, []
    factories = {"demo": lambda _: demo(), "qec": qec, "control": control, "ollama": ollama}
    unknown = set(config) - set(factories)
    if unknown:
        raise ValueError(f"Unknown configuration sections: {sorted(unknown)}")
    for name, factory in factories.items():
        settings = config.get(name, {"enabled": name == "demo"})
        if not isinstance(settings, dict):
            raise ValueError(f"{name} configuration must be an object")
        if "enabled" in settings and type(settings["enabled"]) is not bool:
            raise ValueError(f"{name}.enabled must be a JSON boolean")
        if not settings.get("enabled", name == "demo"):
            connections.append({"id": name, "status": "disabled"})
            continue
        try:
            found = factory(settings)
            for action in found:
                actions[action.id] = action
            connections.append({"id": name, "status": "available", "actions": [a.id for a in found]})
        except (ValueError, OSError, KeyError, TypeError) as error:
            connections.append({"id": name, "status": "unavailable", "reason": str(error)})
    return actions, connections
