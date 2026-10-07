"""Isolated demo, QEC schema probe, and local inference HTTP worker."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
import time
import urllib.request
from urllib.parse import urlsplit


def qec_version(origin):
    for distribution in importlib.metadata.distributions(name="qec"):
        if any(Path(distribution.locate_file(file)).resolve() == origin
               for file in distribution.files or ()):
            return distribution.version
    return "unpackaged-checkout"


def qec_descriptor():
    try:
        provider = importlib.import_module("qec.capabilities")
    except ModuleNotFoundError as error:
        if error.name == "qec.capabilities":
            raise ValueError("QEC has no backend-owned descriptor; install descriptor-capable QEC or explicitly select discovery=legacy-argparse") from error
        raise
    descriptor = provider.descriptor()
    if not isinstance(descriptor, dict) or descriptor.get("protocol") != "qec-capabilities/1":
        raise ValueError("Unsupported QEC descriptor protocol; adapter update required")
    actions, implementation = descriptor.get("actions"), descriptor.get("implementation_modules")
    if not isinstance(actions, list) or not actions or not isinstance(implementation, list) or "qec.capabilities" not in implementation:
        raise ValueError("Malformed QEC descriptor action/implementation list")
    origin = Path(provider.__file__).resolve()
    root = origin.parent
    modules = {}
    names = implementation + [action.get("module") for action in actions if isinstance(action, dict)]
    if len(names) > 64:
        raise ValueError("QEC descriptor has too many implementation modules")
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r"qec(?:\.[A-Za-z_][A-Za-z0-9_]*)+", name):
            raise ValueError("Unsupported QEC module identity")
        # Read reviewed module source without importing scientific CLI parents.
        path = (root.joinpath(*name.split(".")[1:])).with_suffix(".py").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("QEC descriptor module is not a source file in the imported package: " + name)
        modules[name] = {"module_path": str(path), "module_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps({"descriptor": descriptor, "modules": modules,
          "backend": {"kind": "qec", "version": qec_version(origin), "python": sys.executable,
                      "discovery": "descriptor", "descriptor_protocol": descriptor["protocol"]}}))


def qec_probe():
    module = importlib.import_module("qec.benchmark.ququart_battery.cli")
    parser = module.parser()
    fields = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        flags = [flag for flag in action.option_strings if flag.startswith("--")]
        if not flags or action.nargs is not None or type(action) is not argparse._StoreAction:
            raise ValueError(f"Unsupported argparse action: {action.dest}; adapter update required")
        kinds = {None: "string", str: "string", Path: "string", int: "integer", float: "number"}
        if action.type not in kinds:
            raise ValueError(f"Unsupported argument converter: {action.dest}")
        spec = {"name": action.dest, "label": action.dest.replace("_", " ").title(),
                "type": kinds[action.type], "required": action.required,
                "flag": flags[0], "help": action.help or ""}
        if action.default is not None and action.default != argparse.SUPPRESS:
            default = action.default
            # argparse applies the declared converter to string defaults only.
            if isinstance(default, str) and action.type is not None:
                default = action.type(default)
            spec["default"] = str(default) if isinstance(default, Path) else default
        if action.choices is not None:
            spec["choices"] = [str(choice) if isinstance(choice, Path) else choice
                               for choice in action.choices]
        fields.append(spec)
    origin = Path(module.__file__).resolve()
    version = qec_version(origin)
    print(json.dumps({"fields": fields, "backend": {"kind": "qec", "version": version,
          "python": sys.executable, "discovery": "legacy-argparse", "module_path": str(origin),
          "module_sha256": hashlib.sha256(origin.read_bytes()).hexdigest()}}))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Inference endpoint redirects are not supported")


def local_endpoint(url):
    parts = urlsplit(url)
    if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parts.username or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/")):
        raise ValueError("Ollama URL must be an HTTP loopback origin, e.g. http://127.0.0.1:11434")
    return url.rstrip("/")


def inference(mode, url):
    url = local_endpoint(url)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    if mode == "ollama-probe":
        with opener.open(url + "/api/tags", timeout=5) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Model listing exceeds limit")
        result = json.loads(data)
        names = [m["name"] for m in result["models"]]
        if not all(isinstance(n, str) for n in names):
            raise ValueError("Invalid model names")
        print(json.dumps({"models": names}))
        return
    params = json.load(sys.stdin)
    payload = {"model": params["model"], "prompt": params["prompt"], "stream": True,
               "options": {"temperature": params["temperature"], "seed": params["seed"]}}
    request = urllib.request.Request(url + "/api/generate", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    done = False
    # The owning executor enforces the configured wall-clock deadline and
    # cancellation by terminating this worker, including blocked socket reads.
    with opener.open(request, timeout=None) as response:
        while raw := response.readline(1024 * 1024 + 1):
            if len(raw) > 1024 * 1024:
                raise ValueError("Inference event exceeds limit")
            event = json.loads(raw)
            if "error" in event:
                raise ValueError(str(event["error"]))
            print(json.dumps(event), flush=True)
            if event.get("done") is True:
                done = True
                break
    if not done:
        raise ValueError("Inference stream ended without a completion event")


def main():
    mode = sys.argv[1]
    if mode == "demo":
        params = json.load(sys.stdin)
        total = 0
        for index in range(params["steps"]):
            total += (index + 1) * params["seed"]
            print(f"DEMO step {index + 1}/{params['steps']}", file=sys.stderr, flush=True)
            time.sleep(params["delay"])
        print(json.dumps({"demo": True, "label": params["label"], "total": total,
                          "steps": params["steps"], "seed": params["seed"]}))
    elif mode in ("qec-probe", "qec-descriptor"):
        # Match `python -m qec...` only when Python prepends an implicit path.
        # In safe-path mode preserve explicit PYTHONPATH/site paths unchanged.
        if not getattr(sys.flags, "safe_path", False):
            sys.path[0] = str(Path.cwd())
        (qec_probe if mode == "qec-probe" else qec_descriptor)()
    else:
        inference(mode, sys.argv[2])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
