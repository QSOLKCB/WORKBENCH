"""Isolated demo, QEC schema probe, and local inference HTTP worker."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time
import urllib.request
from urllib.parse import urlsplit


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
            spec["default"] = str(action.default) if isinstance(action.default, Path) else action.default
        if action.choices is not None:
            spec["choices"] = list(action.choices)
        fields.append(spec)
    try:
        version = importlib.metadata.version("qec")
    except importlib.metadata.PackageNotFoundError:
        version = "unpackaged-checkout"
    origin = Path(module.__file__).resolve()
    print(json.dumps({"fields": fields, "backend": {"kind": "qec", "version": version,
          "python": sys.executable, "module_path": str(origin),
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
    with opener.open(request, timeout=120) as response:
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
    elif mode == "qec-probe":
        qec_probe()
    else:
        inference(mode, sys.argv[2])


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
