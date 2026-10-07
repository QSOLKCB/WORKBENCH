#!/usr/bin/env python3
"""Run the pinned real-QEC P1 gate; optional tools, never a runtime dependency."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qsol_workbench.model import digest, json_loads
from qsol_workbench.runtime import Runtime
from qsol_workbench.web import make_server

LOCK = ROOT / "examples/qec-p1-lock.json"
MODES = ("direct", "cli", "browser")


def read_json(path):
    return json_loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qec_digest(value):
    # QEC canonical JSON uses unescaped Unicode and forbids floats; these
    # receipts are generated and independently checked by QEC's own validator.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def checked_checksum(value, key, hash_function):
    payload = dict(value)
    expected = payload.pop(key, None)
    if expected != hash_function(payload):
        raise ValueError(f"Invalid {key}")


def verify_artifacts(directory, lock=None):
    lock = lock or read_json(LOCK)
    directory = Path(directory)
    manifest = read_json(directory / "benchmark_manifest.json")
    checked_checksum(manifest, "sha256", qec_digest)
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(lock["expected_artifacts"]):
        raise ValueError("QEC manifest artifact set differs from the pinned contract")
    if manifest.get("schema") != "qec.ququart-fer-battery.v170.1.1" or manifest.get("deterministic") is not True:
        raise ValueError("Unexpected QEC report contract")
    actual = {p.name for p in directory.iterdir()}
    if actual != set(files) | {"benchmark_manifest.json"}:
        raise ValueError("QEC output contains missing or unexpected artifacts")
    for name, expected in files.items():
        path = directory / name
        if Path(name).name != name or path.is_symlink() or not path.is_file() or sha256(path) != expected:
            raise ValueError(f"QEC artifact checksum mismatch: {name}")
    methodology = read_json(directory / "methodology.json")
    checked_checksum(methodology, "sha256", qec_digest)
    parameters = lock["parameters"]
    if (manifest.get("seed") != parameters["seed"] or
            methodology.get("error_rates") != parameters["error_rates"].split(",") or
            methodology["monte_carlo"]["trials_per_cell"] != parameters["trials"] or
            methodology["monte_carlo"]["seed"] != parameters["seed"] or
            methodology["harmonic_receiver"]["end_to_end_trials_per_cell"] != parameters["harmonic_trials"] or
            methodology["sha256"] != manifest.get("methodology_sha256")):
        raise ValueError("QEC methodology does not describe the requested inputs")
    return manifest


def compare_reports(directories, lock=None):
    manifests = [verify_artifacts(directory, lock) for directory in directories]
    if any(manifest != manifests[0] for manifest in manifests[1:]):
        raise ValueError("Direct, CLI and browser scientific artifacts differ")
    return {"byte_identical": True, "manifest_sha256": manifests[0]["sha256"],
            "artifact_count_per_mode": len(manifests[0]["files"]) + 1,
            "normalized_fields": [], "note": "No path/timestamp exclusions were needed."}


def verify_record(record, parameters, status, environment):
    checked_checksum(record, "record_sha256", digest)
    if (record.get("protocol") != "qsol-workbench-run/1" or
            record.get("action") != "qec.ququart.benchmark" or record.get("parameters") != parameters or
            record.get("status") != status or record.get("persistence_error")):
        raise ValueError("WORKBENCH run does not match the requested action, inputs or outcome")
    expected_exit = 0 if status == "succeeded" else 1
    if record.get("exit_code") != expected_exit or record.get("transport_status") != status:
        raise ValueError("WORKBENCH transport outcome differs from QEC")
    backend = record["capability"]["backend"]
    if (backend.get("python") != environment["executable"] or
            backend.get("version") != environment["packages"]["qec"]["version"] or
            backend.get("module_sha256") != environment["cli_sha256"] or
            record["execution"]["argv"][0] != environment["executable"]):
        raise ValueError("WORKBENCH used a different QEC interpreter or module")
    capability = dict(record["capability"])
    checked_checksum(capability, "schema_sha256", digest)
    if status == "failed" and "trials must be positive" not in record.get("stderr", ""):
        raise ValueError("The negative run did not reach QEC's own trial validation")


def verify_validation(receipt, directory):
    if receipt.get("schema") != "qec.ququart-report-claim-validation.v1" or receipt.get("passed") is not True:
        raise ValueError("QEC report validation did not pass")
    checked_checksum(receipt, "sha256", qec_digest)
    if receipt.get("claims_sha256") != qec_digest(read_json(Path(directory) / "report_claims.json")):
        raise ValueError("QEC validation receipt belongs to different claims")
    if receipt != read_json(Path(directory) / "claim_validation.json"):
        raise ValueError("Independent QEC validation disagrees with generated validation")


def verify_environment(environment, lock):
    expected = lock["environment"]
    if (not environment["platform"].startswith(expected["os"] + "-") or
            environment["architecture"] != expected["architecture"] or
            environment["python"].split()[0] != expected["python"] or
            any(environment["packages"][name]["version"] != version for name, version in lock["dependencies"].items())):
        raise ValueError("Environment differs from the first supported P1 matrix")


def seal(directory):
    directory = Path(directory)
    lines = [f"{sha256(path)}  {path.relative_to(directory).as_posix()}"
             for path in sorted(directory.rglob("*")) if path.is_file() and path != directory / "SHA256SUMS"]
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_evidence(directory):
    directory = Path(directory).resolve()
    entries = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        path = directory / name
        if name in entries or path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ValueError("Duplicate or unsafe evidence inventory entry")
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"Evidence checksum mismatch: {name}")
        entries[name] = expected
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file() and p != directory / "SHA256SUMS"}
    if set(entries) != actual:
        raise ValueError("Incomplete evidence inventory")
    lock, summary = read_json(directory / "lock.json"), read_json(directory / "summary.json")
    if lock != read_json(LOCK) or summary.get("status") != "passed" or summary.get("modes") != list(MODES):
        raise ValueError("Evidence is not a complete pinned P1 acceptance run")
    environment = read_json(directory / "environment.json")
    verify_environment(environment, lock)
    source = read_json(directory / "qec-source.json")
    if (source["commit"] != lock["commit"] or summary.get("qec_commit") != lock["commit"] or
            source["installed_matches_source"] is not True or
            source["python_files"].get("benchmark/ququart_battery/cli.py") != environment["cli_sha256"] or
            environment["packages"]["qec"]["version"] != lock["package_version"] or
            environment["prefix"] == environment["base_prefix"]):
        raise ValueError("QEC source identity mismatch")
    if read_json(directory / "commands/pip-check.json")["exit_code"] != 0:
        raise ValueError("Recorded QEC environment has unsatisfied dependencies")
    for mode in MODES:
        report = directory / "artifacts" / mode
        manifest = verify_artifacts(report, lock)
        validation = read_json(directory / "validation" / (mode + ".json"))
        verify_validation(validation, report)
        command = read_json(directory / "commands" / ("validate-" + mode + ".json"))
        if command["exit_code"] != 0 or read_json(directory / command["stdout"]) != validation:
            raise ValueError("QEC validator execution did not produce this receipt")
        if mode != "direct":
            for case, status in [("success", "succeeded"), ("failure", "failed")]:
                record = read_json(directory / "runs" / f"{mode}-{case}.json")
                parameters = {**lock["parameters" if case == "success" else "failure_parameters"],
                              "output": str(Path(summary["output_directory"]) / "artifacts" /
                                            (mode if case == "success" else mode + "-failure"))}
                verify_record(record, parameters, status, environment)
                if read_json(directory / "store" / (record["id"] + ".json")) != record:
                    raise ValueError("Exported WORKBENCH record differs from its persisted snapshot")
                if mode == "cli":
                    cli_command = read_json(directory / "commands" / f"cli-{case}.json")
                    if (cli_command["exit_code"] != (0 if case == "success" else 1) or
                            read_json(directory / cli_command["stdout"]) != record):
                        raise ValueError("CLI outcome differs from the retained record")
                if case == "success" and record["result"] != manifest:
                    raise ValueError("WORKBENCH returned a different scientific manifest")
    for case, exit_code in [("success", 0), ("failure", 1)]:
        command = read_json(directory / "commands" / f"direct-{case}.json")
        if command["exit_code"] != exit_code:
            raise ValueError("Direct QEC command outcome mismatch")
        if case == "success" and read_json(directory / command["stdout"]) != verify_artifacts(directory / "artifacts/direct", lock):
            raise ValueError("Direct QEC stdout differs from its artifacts")
        if case == "failure" and "trials must be positive" not in (directory / command["stderr"]).read_text():
            raise ValueError("Direct failure did not reach QEC validation")
    browser = read_json(directory / "browser.json")
    if browser.get("status") != "passed" or browser.get("exceptions") or not browser.get("engine", "").startswith(("Chromium ", "Google Chrome ")):
        raise ValueError("Missing successful real-browser evidence")
    records = [read_json(directory / "runs" / f"browser-{case}.json") for case in ("success", "failure")]
    if [run["id"] for run in browser["runs"]] != [record["id"] for record in records]:
        raise ValueError("Browser receipt refers to different runs")
    for run, record in zip(browser["runs"], records):
        if (run["status"] != record["status"] or run["parameters"] != record["parameters"] or
                run["expected_status"] != record["status"] or
                run["schema_sha256"] != record["capability"]["schema_sha256"]):
            raise ValueError("Browser receipt differs from its saved run")
    if read_json(directory / "commands/browser.json")["exit_code"] != 0:
        raise ValueError("Browser driver failed")
    negative = read_json(directory / "commands/validate-negative.json")
    if negative["exit_code"] == 0 or "ReportClaimError" not in (directory / negative["stderr"]).read_text():
        raise ValueError("QEC did not reject the intentionally invalid report claim")
    comparison = compare_reports([directory / "artifacts" / mode for mode in MODES], lock)
    if summary.get("comparison") != comparison:
        raise ValueError("Stored comparison disagrees with the retained artifacts")
    return comparison


def run_acceptance(args):
    lock = read_json(LOCK)
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    qec_root = Path(args.qec_root).expanduser().resolve()
    python = os.path.abspath(Path(args.python).expanduser())  # Preserve the venv symlink.
    env = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    summary = {"protocol": "qsol-workbench-p1/1", "status": "running", "modes": list(MODES),
               "started_at": datetime.now(timezone.utc).isoformat(), "output_directory": str(output),
               "qec_commit": lock["commit"], "claim_scope": lock["claim_scope"]}
    write_json(output / "lock.json", lock)
    if args.setup_receipt:
        shutil.copyfile(args.setup_receipt, output / "setup.json")

    def capture(name, argv, cwd=qec_root, command_env=env):
        started = time.monotonic()
        stdout_path, stderr_path = f"commands/{name}.stdout", f"commands/{name}.stderr"
        try:
            completed = subprocess.run(argv, cwd=cwd, env=command_env, capture_output=True,
                                       text=True, timeout=args.timeout + 15)
            code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as error:
            code = None
            stdout, stderr = error.stdout or b"", error.stderr or b""
            stdout = stdout.decode(errors="replace") if isinstance(stdout, bytes) else stdout
            stderr = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
            stderr += "\nAcceptance command deadline reached\n"
        (output / "commands").mkdir(exist_ok=True)
        (output / stdout_path).write_text(stdout, encoding="utf-8")
        (output / stderr_path).write_text(stderr, encoding="utf-8")
        write_json(output / f"commands/{name}.json", {"argv": argv, "cwd": str(cwd), "exit_code": code,
                   "duration_seconds": round(time.monotonic() - started, 4), "stdout": stdout_path, "stderr": stderr_path})
        return code, stdout, stderr

    try:
        code, head, _ = capture("source-head", ["git", "rev-parse", "HEAD"])
        if code or head.strip() != lock["commit"]:
            raise ValueError("QEC checkout differs from the pinned commit")
        code, status, _ = capture("source-status", ["git", "status", "--porcelain", "--untracked-files=all"])
        if code or status.strip():
            raise ValueError("QEC checkout is dirty; use a pristine pinned checkout")
        code, tracked, _ = capture("source-files", ["git", "ls-files", "src/qec"])
        if code:
            raise ValueError("Cannot inventory pinned QEC source")
        source_hashes = {str(Path(name).relative_to("src/qec")): sha256(qec_root / name)
                         for name in tracked.splitlines() if name.endswith(".py")}
        identity_code = """import hashlib,importlib.metadata as m,json,platform,sys,sysconfig
import qec, qec.benchmark.ququart_battery.cli as cli
from pathlib import Path
root=Path(qec.__file__).parent
packages={}
for name in ('qec','numpy','scipy','pip','setuptools','wheel'):
 try:
  d=m.distribution(name); packages[name]={'version':d.version,'requires':d.requires or []}
 except m.PackageNotFoundError: packages[name]={'version':None,'requires':[]}
print(json.dumps({'executable':sys.executable,'python':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,
 'platform':platform.platform(),'architecture':platform.machine(),'purelib':sysconfig.get_path('purelib'),
 'packages':packages,'cli_path':cli.__file__,'cli_sha256':hashlib.sha256(Path(cli.__file__).read_bytes()).hexdigest(),
 'module_files':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*.py'))}}))
"""
        code, text, _ = capture("environment", [python, "-c", identity_code])
        if code:
            raise ValueError("Selected interpreter cannot import real QEC")
        environment = json_loads(text)
        installed_hashes = environment.pop("module_files")
        write_json(output / "environment.json", environment)
        verify_environment(environment, lock)
        if (installed_hashes != source_hashes or environment["executable"] != python or
                environment["packages"]["qec"]["version"] != lock["package_version"] or
                environment["prefix"] == environment["base_prefix"]):
            raise ValueError("Install the pinned, unmodified QEC package into a separate venv")
        write_json(output / "qec-source.json", {"repository": lock["repository"], "commit": head.strip(),
                   "installed_matches_source": True, "python_files": source_hashes})
        code, _, _ = capture("pip-check", [python, "-m", "pip", "check"])
        if code:
            raise ValueError("QEC environment has unsatisfied package dependencies")
        code, _, _ = capture("pip-freeze", [python, "-m", "pip", "freeze", "--all"])
        if code:
            raise ValueError("Cannot retain installed dependency versions")
        files = [p for p in (ROOT / "src/qsol_workbench").rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".html", ".css")]
        write_json(output / "workbench-source.json", {"version": "0.1.0",
            "files": {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(files)}})
        config = {"demo": {"enabled": False}, "qec": {"enabled": True, "python": python, "cwd": str(qec_root)}}
        write_json(output / "config.json", config)
        runtime = Runtime(config, output / "store", timeout=args.timeout)
        server = None
        try:
            if lock["action"] not in runtime.actions:
                raise ValueError("Real QEC discovery failed: " + json.dumps(runtime.connections))
            write_json(output / "discovery.json", runtime.manifest())
            cases = []
            for mode in MODES:
                for case, expected in (("success", "succeeded"), ("failure", "failed")):
                    params = {**lock["parameters" if case == "success" else "failure_parameters"],
                              "output": str(output / "artifacts" / (mode if case == "success" else mode + "-failure"))}
                    if mode == "browser":
                        cases.append({"name": case, "parameters": params, "status": expected,
                                      "record": str(output / "runs" / f"browser-{case}.json")})
                        continue
                    argv = [python, "-m", lock["module"]] + ["--" + name.replace("_", "-") + "=" + str(value) for name, value in params.items()]
                    if mode == "cli":
                        argv = [sys.executable, str(ROOT / "workbench.py"), "--config", str(output / "config.json"),
                                "--store", str(output / "store"), "--timeout", str(args.timeout), "run", lock["action"], "--params", json.dumps(params)]
                    code, text, stderr = capture(f"{mode}-{case}", argv, ROOT if mode == "cli" else qec_root)
                    if code != (0 if case == "success" else 1):
                        raise ValueError(f"Unexpected {mode} {case} exit: {code}: {stderr[-1000:]}")
                    if mode == "cli":
                        record = json_loads(text)
                        write_json(output / "runs" / f"{mode}-{case}.json", record)
                        verify_record(record, params, expected, environment)
                    elif case == "success" and json_loads(text) != verify_artifacts(output / "artifacts/direct", lock):
                        raise ValueError("Direct output differs from its scientific manifest")
                    elif case == "failure" and "trials must be positive" not in stderr:
                        raise ValueError("Direct negative run did not reach QEC trial validation")
            (output / "runs").mkdir(exist_ok=True)
            write_json(output / "browser-cases.json", cases)
            server = make_server(runtime, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            browser_env = {**env, "BROWSER_BIN": args.browser_bin,
                           "WORKBENCH_URL": f"http://127.0.0.1:{server.server_port}/#token={server.workbench_token}"}
            code, _, stderr = capture("browser", ["node", str(ROOT / "tools/qec_browser.mjs"),
                         str(output / "browser-cases.json"), str(output / "browser.json"), str(args.timeout)], ROOT, browser_env)
            if code:
                raise ValueError("Real-browser acceptance failed: " + stderr[-1000:])
        finally:
            if server:
                server.shutdown(); server.server_close()
            runtime.close()
        for mode in MODES:
            report = output / "artifacts" / mode
            verify_artifacts(report, lock)
            receipt_path = output / "validation" / (mode + ".json")
            receipt_path.parent.mkdir(exist_ok=True)
            code, text, stderr = capture("validate-" + mode, [python, "-m", lock["validator"],
                         "--claims", str(report / "report_claims.json"), "--evidence", str(report), "--output", str(receipt_path)])
            if code:
                raise ValueError("QEC report validator rejected " + mode + ": " + stderr[-1000:])
            verify_validation(json_loads(text), report)
        negative = read_json(output / "artifacts/direct/report_claims.json")
        negative.pop("sha256")
        negative["threshold_claim"] = True
        negative["sha256"] = qec_digest(negative)
        write_json(output / "negative-claims.json", negative)
        code, _, stderr = capture("validate-negative", [python, "-m", lock["validator"],
                     "--claims", str(output / "negative-claims.json"), "--evidence", str(output / "artifacts/direct")])
        if code != 1 or "ReportClaimError" not in stderr:
            raise ValueError("QEC did not reject the intentionally invalid threshold claim")
        summary["comparison"] = compare_reports([output / "artifacts" / mode for mode in MODES], lock)
        summary["status"] = "passed"
    except Exception as error:
        summary["status"] = "failed"
        summary["error"] = f"{type(error).__name__}: {error}"
    finally:
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "summary.json", summary)
        seal(output)
    if summary["status"] != "passed":
        raise ValueError(summary["error"])
    try:
        verify_evidence(output)
    except Exception as error:
        summary.update(status="failed", error=f"Evidence verification failed: {type(error).__name__}: {error}")
        write_json(output / "summary.json", summary)
        seal(output)
        raise
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", metavar="EVIDENCE", help="Verify retained P1 evidence without QEC or a browser")
    parser.add_argument("--qec-root")
    parser.add_argument("--python")
    parser.add_argument("--browser-bin", default=os.environ.get("BROWSER_BIN", "google-chrome"))
    parser.add_argument("--output")
    parser.add_argument("--setup-receipt", help="Optional retained environment-preparation transcript")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_evidence(args.verify)
        else:
            if not args.qec_root or not args.python or not args.output:
                parser.error("--qec-root, --python and a fresh --output directory are required")
            if not 0 < args.timeout <= 86400:
                parser.error("--timeout must be between 0 and 86400 seconds")
            result = run_acceptance(args)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"P1 acceptance error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
