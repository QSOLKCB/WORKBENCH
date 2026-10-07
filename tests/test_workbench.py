"""Behavior and integration-contract tests; no model or QEC install required."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import http.client
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qsol_workbench.adapters.builtin import check_control
from qsol_workbench.model import Plan, digest, field, json_loads, validate
from qsol_workbench.process import execute
from qsol_workbench.runtime import Runtime
from qsol_workbench.web import make_server
from qsol_workbench.cli import main as cli_main
from qsol_workbench.tui import launch
from qsol_workbench.worker import inference


@contextmanager
def runtime(config=None, **kwargs):
    with tempfile.TemporaryDirectory() as directory:
        instance = Runtime(config, Path(directory) / "runs", **kwargs)
        try:
            yield instance
        finally:
            instance.close()


class ContractTests(unittest.TestCase):
    def test_validation_rejects_unknown_bool_alias_and_nonfinite(self):
        specs = [field("n", "integer", required=True, minimum=1, maximum=5)]
        for params in ({"n": True}, {"n": 0}, {"n": 6}, {"n": "3"}, {"n": 3, "x": 1}, {}):
            with self.assertRaises(ValueError):
                validate(specs, params)
        self.assertEqual(validate(specs, {"n": 3}), {"n": 3})
        for text in ('{"a":1,"a":2}', '{"n":NaN}', '{"n":1e999}'):
            with self.assertRaises(ValueError):
                json_loads(text)

    def test_choices_and_defaults(self):
        specs = [field("mode", default="fast", choices=["fast", "slow"])]
        self.assertEqual(validate(specs, {}), {"mode": "fast"})
        with self.assertRaises(ValueError):
            validate(specs, {"mode": "other"})

    def test_control_error_and_wrong_correlation_rejected(self):
        good = {"protocol": "qsol-control-agent-response/1", "request_id": "workbench-request",
                "operation": "control.health", "ok": True, "result": {}, "authority": "orchestration-only"}
        self.assertEqual(check_control(good, "control.health"), good)
        for changed in ({"ok": False}, {"request_id": "other"}, {"operation": "control.ask"},
                        {"protocol": "qsol-control-agent-error/1"}):
            with self.assertRaises(ValueError):
                check_control({**good, **changed}, "control.health")


class ProcessTests(unittest.TestCase):
    def test_subprocess_is_not_a_shell(self):
        text = "$(touch should-not-exist); `echo nope`"
        result = execute(Plan([sys.executable, "-c", "import sys; print(sys.argv[1])", text]))
        self.assertEqual(result["stdout"].strip(), text)
        self.assertEqual(result["status"], "succeeded")

    def test_nonzero_exit_retains_stderr(self):
        result = execute(Plan([sys.executable, "-c", "import sys; print('broken',file=sys.stderr); sys.exit(7)"]))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 7)
        self.assertIn("broken", result["stderr"])

    def test_output_bound_and_timeout(self):
        result = execute(Plan([sys.executable, "-c", "print('x'*100000)"]), max_output=1024)
        self.assertEqual(result["status"], "output_limit")
        self.assertLessEqual(len(result["stdout"]), 1024)
        result = execute(Plan([sys.executable, "-c", "import time; time.sleep(10)"]), timeout=.1)
        self.assertEqual(result["status"], "timed_out")

    def test_cancel_running_process(self):
        cancel = threading.Event()
        timer = threading.Timer(.1, cancel.set)
        timer.start()
        result = execute(Plan([sys.executable, "-c", "import time; time.sleep(10)"]), cancel=cancel)
        timer.join()
        self.assertEqual(result["status"], "cancelled")

    @unittest.skipUnless(os.name == "posix", "Process groups are POSIX-only")
    def test_descendant_with_open_pipe_obeys_deadline(self):
        program = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])"
        started = time.monotonic()
        result = execute(Plan([sys.executable, "-c", program]), timeout=.2)
        self.assertEqual(result["status"], "timed_out")
        self.assertLess(time.monotonic() - started, 3)


class RuntimeTests(unittest.TestCase):
    def test_bad_configuration_is_not_silently_enabled(self):
        with self.assertRaises(ValueError):
            with runtime({"qec": {"enabled": "false"}}):
                pass

    def test_invalid_backend_json_is_a_failed_run(self):
        with runtime() as instance:
            instance.actions["demo.experiment"].build = lambda p: Plan([sys.executable, "-c", "print('not JSON')"])
            job = instance.start("demo.experiment", {})
            result = instance.wait(job["id"])
            self.assertEqual(result["status"], "failed")
            self.assertIn("not JSON", result["stdout"])
            self.assertIsNotNone(result["error"])

    def test_protocol_failures_preserve_zero_exit_transport_results(self):
        cases = [("json", "not JSON"),
                 ("control", '{"protocol":"wrong"}'),
                 ("ollama", '{"response":"partial","done":false}\n')]
        for kind, output in cases:
            with self.subTest(kind=kind), runtime() as instance:
                instance.actions["demo.experiment"].build = lambda p: Plan(
                    [sys.executable, "-c", "import sys; print('diagnostic',file=sys.stderr); print(" + repr(output) + ")"],
                    result_kind=kind, expected_operation="control.health")
                job = instance.start("demo.experiment", {})
                result = instance.wait(job["id"])
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["exit_code"], 0)
                self.assertEqual(result["transport_status"], "succeeded")
                self.assertEqual(result["stdout"].strip(), output.strip())
                self.assertIn("diagnostic", result["stderr"])
                self.assertIsNone(result["result"])
                self.assertIsNotNone(result["error"])
                self.assertEqual(json_loads((instance.store / (job["id"] + ".json")).read_text()), result)

    def test_surrogate_encoding_failure_reports_unsaved_final_record(self):
        with runtime() as instance:
            instance.actions["demo.experiment"].build = lambda p: Plan(
                [sys.executable, "-c", "print(" + repr('{"text":"\\ud800"}') + ")"])
            with patch("threading.excepthook") as uncaught:
                job = instance.start("demo.experiment", {})
                result = instance.wait(job["id"])
                uncaught.assert_not_called()
            self.assertEqual(result["exit_code"], 0)
            self.assertIn("persistence_error", result)
            self.assertNotIn("record_sha256", result)
            self.assertEqual(result["result"]["text"], "\ud800")
            saved = json_loads((instance.store / (job["id"] + ".json")).read_text())
            self.assertEqual(saved["status"], "queued")
            other = Runtime(store=instance.store)
            try:
                self.assertEqual(other.get(job["id"])["status"], "interrupted")
            finally:
                other.close()

    def test_cli_encoding_failure_returns_nonzero_and_printable_json(self):
        with runtime() as instance:
            instance.actions["demo.experiment"].build = lambda p: Plan(
                [sys.executable, "-c", "print(" + repr('{"text":"\\ud800"}') + ")"])
            output = io.StringIO()
            with patch("qsol_workbench.cli.Runtime", return_value=instance), redirect_stdout(output):
                code = cli_main(["run", "demo.experiment"])
            self.assertEqual(code, 1)
            encoded = output.getvalue().encode("utf-8")
            self.assertIn("persistence_error", json_loads(encoded))

    def test_final_serialization_failure_is_visible_without_rehashing(self):
        for error in (ValueError("serialization rejected"), TypeError("unserializable value"), OSError("disk full")):
            with self.subTest(error=type(error).__name__), runtime() as instance:
                save = instance._save
                def fail_final(record):
                    if record["status"] in {"queued", "running"}:
                        return save(record)
                    raise error
                with patch.object(instance, "_save", side_effect=fail_final), patch("threading.excepthook") as uncaught:
                    job = instance.start("demo.experiment", {"delay": 0})
                    result = instance.wait(job["id"])
                    uncaught.assert_not_called()
                self.assertIn("persistence_error", result)
                self.assertNotIn("record_sha256", result)

    def test_tui_history_renders_legacy_unfinished_record_without_outputs(self):
        with runtime() as instance:
            run_id = "e" * 32
            record = {"protocol": "qsol-workbench-run/1", "id": run_id,
                      "status": "queued", "error": None}
            (instance.store / (run_id + ".json")).write_text(json.dumps(record))
            screen = MagicMock()
            screen.getmaxyx.return_value = (30, 120)
            screen.getch.side_effect = [ord("h"), ord("q")]
            with patch("qsol_workbench.tui.curses.wrapper", side_effect=lambda app: app(screen)), patch("qsol_workbench.tui.curses.curs_set"):
                launch(instance)
            rendered = " ".join(call.args[2] for call in screen.addnstr.call_args_list)
            self.assertIn("interrupted", rendered)
            self.assertIn("Owner process ended", rendered)

    def test_job_limit_and_refresh_during_execution(self):
        with runtime() as instance:
            for _ in range(4):
                instance.start("demo.experiment", {"steps": 100, "delay": 1})
            with self.assertRaises(ValueError):
                instance.start("demo.experiment", {})
            with self.assertRaises(ValueError):
                instance.refresh()

    def test_demo_executes_persists_and_checksum_verifies(self):
        with runtime() as instance:
            job = instance.start("demo.experiment", {"steps": 3, "seed": 7, "delay": 0})
            record = instance.wait(job["id"])
            self.assertEqual(record["status"], "succeeded")
            self.assertEqual(record["result"]["total"], 42)
            self.assertIn("DEMO", record["stderr"])
            stored = json_loads((instance.store / (job["id"] + ".json")).read_text())
            checksum = stored.pop("record_sha256")
            self.assertEqual(checksum, digest(stored))
            self.assertEqual(instance.history()[0]["status"], "succeeded")
            other = Runtime(store=instance.store)
            try:
                self.assertEqual(other.get(job["id"])["result"]["total"], 42)
            finally:
                other.close()

    def test_schema_change_requires_new_form(self):
        with runtime() as instance:
            with self.assertRaisesRegex(ValueError, "schema changed"):
                instance.start("demo.experiment", {}, "stale")
            self.assertEqual(instance.history(), [])

    def test_disk_reload_rejects_tampering_and_missing_final_checksum(self):
        with runtime() as instance:
            job = instance.start("demo.experiment", {"steps": 3, "seed": 7, "delay": 0})
            instance.wait(job["id"])
            path = instance.store / (job["id"] + ".json")
            original = json_loads(path.read_text())
            other = Runtime(store=instance.store)
            try:
                changed = deepcopy(original)
                changed["result"]["total"] = 99
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    other.get(job["id"])
                self.assertEqual(other.history(), [])
                for checksum in (None, "bad", 7):
                    changed = deepcopy(original)
                    if checksum is None:
                        changed.pop("record_sha256")
                    else:
                        changed["record_sha256"] = checksum
                    path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError, "checksum"):
                        other.get(job["id"])
                path.write_text(json.dumps(original))
                self.assertEqual(other.get(job["id"]), original)
            finally:
                other.close()

    def test_interrupted_view_preserves_verified_stored_record(self):
        with runtime() as instance:
            run_id = "a" * 32
            saved = {"protocol": "qsol-workbench-run/1", "id": run_id,
                     "status": "queued", "error": None}
            instance._save(saved)
            path = instance.store / (run_id + ".json")
            before = path.read_bytes()
            view = instance.get(run_id)
            self.assertEqual(view["status"], "interrupted")
            self.assertNotIn("record_sha256", view)
            self.assertEqual(view["stored_record_integrity"], "verified")
            self.assertEqual(view["stored_record"], saved)
            body = deepcopy(view["stored_record"])
            self.assertEqual(body.pop("record_sha256"), digest(body))
            self.assertEqual(path.read_bytes(), before)
            saved["error"] = "modified after saving"
            path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                instance.get(run_id)

    def test_legacy_unfinished_record_is_explicitly_unverified(self):
        with runtime() as instance:
            run_id = "b" * 32
            record = {"protocol": "qsol-workbench-run/1", "id": run_id,
                      "status": "queued", "error": None}
            (instance.store / (run_id + ".json")).write_text(json.dumps(record))
            view = instance.get(run_id)
            self.assertEqual(view["stored_record_integrity"], "unverified")
            self.assertEqual(view["stored_record"], record)
            self.assertNotIn("record_sha256", view)

    def test_malformed_or_misidentified_disk_record_is_rejected(self):
        with runtime() as instance:
            run_id = "c" * 32
            path = instance.store / (run_id + ".json")
            base = {"protocol": "qsol-workbench-run/1", "id": run_id, "status": "queued"}
            for value in ([], {**base, "id": "d" * 32}, {**base, "protocol": "other"},
                          {**base, "status": []}, {**base, "status": "unknown"}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    instance.get(run_id)

    def test_cli_show_reports_corrupted_disk_record(self):
        with runtime() as instance:
            job = instance.start("demo.experiment", {"steps": 3, "seed": 7, "delay": 0})
            instance.wait(job["id"])
            path = instance.store / (job["id"] + ".json")
            record = json_loads(path.read_text())
            record["parameters"]["seed"] = 8
            path.write_text(json.dumps(record))
            completed = subprocess.run(
                [sys.executable, str(ROOT / "workbench.py"), "--store", str(instance.store),
                 "show", job["id"]], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("checksum mismatch", completed.stderr)
            self.assertEqual(completed.stdout, "")

    def test_unavailable_backend_never_uses_demo(self):
        with runtime({"qec": {"enabled": True, "python": "/not-a-python"}}) as instance:
            connection = next(c for c in instance.connections if c["id"] == "qec")
            self.assertEqual(connection["status"], "unavailable")
            with self.assertRaises(ValueError):
                instance.start("qec.ququart.benchmark", {})

    def test_cancel_record_is_not_success(self):
        with runtime() as instance:
            job = instance.start("demo.experiment", {"delay": 1, "steps": 20})
            instance.cancel(job["id"])
            self.assertEqual(instance.wait(job["id"])["status"], "cancelled")

    def test_path_traversal_rejected(self):
        with runtime() as instance:
            with self.assertRaises(ValueError):
                instance.get("../../etc/passwd")


class AdapterTests(unittest.TestCase):
    def test_qec_path_choices_match_direct_argparse_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "qec/benchmark/ququart_battery/cli.py"
            module.parent.mkdir(parents=True)
            for parent in [root / "qec", root / "qec/benchmark", module.parent]:
                (parent / "__init__.py").write_text("")
            module.write_text(
                "import argparse,json\nfrom pathlib import Path\n"
                "def parser():\n p=argparse.ArgumentParser()\n"
                " p.add_argument('--output',type=Path,choices=[Path('a'),Path('b')],default=Path('a'))\n"
                " return p\n"
                "if __name__=='__main__': print(json.dumps(vars(parser().parse_args()),default=str))\n")
            with patch.dict(os.environ):
                os.environ.pop("PYTHONSAFEPATH", None)
                os.environ.pop("PYTHONPATH", None)
                with runtime({"qec": {"enabled": True, "python": sys.executable, "cwd": directory}}) as instance:
                    connection = next(c for c in instance.connections if c["id"] == "qec")
                    self.assertEqual(connection["status"], "available", connection)
                    action = instance.actions["qec.ququart.benchmark"]
                    spec = action.public()["fields"][0]
                    self.assertEqual(spec["choices"], ["a", "b"])
                    self.assertEqual(spec["default"], "a")
                    for params in ({}, {"output": "b"}):
                        argv = [sys.executable, "-m", "qec.benchmark.ququart_battery.cli"]
                        if params:
                            argv.append("--output=" + params["output"])
                        direct = subprocess.run(argv, cwd=root, check=True, capture_output=True, text=True)
                        job = instance.start(action.id, params)
                        record = instance.wait(job["id"])
                        self.assertEqual(record["status"], "succeeded", record)
                        self.assertEqual(record["result"], json_loads(direct.stdout))
                    with self.assertRaisesRegex(ValueError, "one of"):
                        instance.start(action.id, {"output": "c"})

    def test_qec_version_metadata_must_own_the_imported_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            foreign = root / "foreign"
            module = checkout / "qec/benchmark/ququart_battery/cli.py"
            module.parent.mkdir(parents=True)
            for parent in [checkout / "qec", checkout / "qec/benchmark", module.parent]:
                (parent / "__init__.py").write_text("")
            module.write_text("import argparse,json\ndef parser(): return argparse.ArgumentParser()\nif __name__=='__main__': print(json.dumps({'fixture':True}))\n")
            foreign_metadata = foreign / "qec-9.9.dist-info"
            foreign_metadata.mkdir(parents=True)
            (foreign_metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: qec\nVersion: 9.9\n")
            (foreign_metadata / "RECORD").write_text("qec/benchmark/ququart_battery/cli.py,,\n")
            own_metadata = checkout / "qec-1.2.dist-info"
            for scenario, version in [("foreign", "unpackaged-checkout"), ("owned", "1.2"), ("unlisted", "unpackaged-checkout")]:
                with self.subTest(scenario=scenario), patch.dict(os.environ):
                    if scenario == "owned":
                        own_metadata.mkdir()
                        (own_metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: qec\nVersion: 1.2\n")
                        (own_metadata / "RECORD").write_text("qec/benchmark/ququart_battery/cli.py,,\n")
                    elif scenario == "unlisted":
                        (own_metadata / "RECORD").unlink()
                    # Search unrelated metadata first, then the actual code.
                    os.environ["PYTHONPATH"] = os.pathsep.join([str(foreign), str(checkout)])
                    os.environ["PYTHONSAFEPATH"] = "1"
                    direct = subprocess.run([sys.executable, "-m", "qec.benchmark.ququart_battery.cli"],
                                            cwd=checkout, check=True, capture_output=True, text=True)
                    with runtime({"qec": {"enabled": True, "python": sys.executable, "cwd": str(checkout)}}) as instance:
                        action = instance.actions["qec.ququart.benchmark"]
                        self.assertEqual(action.backend["module_path"], str(module))
                        self.assertEqual(action.backend["module_sha256"], hashlib.sha256(module.read_bytes()).hexdigest())
                        self.assertEqual(action.backend["version"], version)
                        job = instance.start(action.id, {})
                        record = instance.wait(job["id"])
                        self.assertEqual(record["status"], "succeeded", record)
                        self.assertEqual(record["capability"]["backend"]["version"], version)
                        self.assertEqual(record["result"], json_loads(direct.stdout))

    @unittest.skipUnless(sys.version_info >= (3, 11), "Safe-path mode requires Python 3.11+")
    def test_qec_probe_follows_execution_import_rules_in_safe_path_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "backend"
            unrelated = root / "unrelated"
            unrelated.mkdir()
            module = backend / "qec/benchmark/ququart_battery/cli.py"
            module.parent.mkdir(parents=True)
            for parent in [backend / "qec", backend / "qec/benchmark", module.parent]:
                (parent / "__init__.py").write_text("")
            module.write_text(
                "import argparse,json\n"
                "def parser():\n return argparse.ArgumentParser()\n"
                "if __name__=='__main__': print(json.dumps({'fixture':True}))\n")
            cases = [(False, None, backend, True),
                     (True, None, backend, False),
                     (True, str(backend), unrelated, True)]
            for safe_path, python_path, cwd, available in cases:
                with self.subTest(safe_path=safe_path, python_path=python_path), patch.dict(os.environ):
                    os.environ.pop("PYTHONSAFEPATH", None)
                    os.environ.pop("PYTHONPATH", None)
                    if safe_path:
                        os.environ["PYTHONSAFEPATH"] = "1"
                    if python_path is not None:
                        os.environ["PYTHONPATH"] = python_path
                    direct = subprocess.run([sys.executable, "-m", "qec.benchmark.ququart_battery.cli"],
                                            cwd=cwd, capture_output=True, text=True)
                    self.assertEqual(direct.returncode == 0, available, direct.stderr)
                    with runtime({"qec": {"enabled": True, "python": sys.executable, "cwd": str(cwd)}}) as instance:
                        connection = next(c for c in instance.connections if c["id"] == "qec")
                        self.assertEqual(connection["status"], "available" if available else "unavailable", connection)
                        if available:
                            action = instance.actions["qec.ququart.benchmark"]
                            self.assertEqual(action.backend["module_path"], str(module))
                            job = instance.start(action.id, {})
                            record = instance.wait(job["id"])
                            self.assertEqual(record["status"], "succeeded", record)
                            self.assertEqual(record["result"], json_loads(direct.stdout))
                        else:
                            self.assertIn("ModuleNotFoundError", connection["reason"])
                            self.assertNotIn("qec.ququart.benchmark", instance.actions)
                            with self.assertRaisesRegex(ValueError, "unavailable"):
                                instance.start("qec.ququart.benchmark", {})

    def test_uninstalled_qec_checkout_and_converted_string_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "qec/benchmark/ququart_battery/cli.py"
            module.parent.mkdir(parents=True)
            for parent in [root / "qec", root / "qec/benchmark", module.parent]:
                (parent / "__init__.py").write_text("")
            module.write_text(
                "import argparse,json\nfrom pathlib import Path\n"
                "def parser():\n p=argparse.ArgumentParser()\n"
                " p.add_argument('--trials',type=int,default='10')\n"
                " p.add_argument('--rate',type=float,default='0.25')\n"
                " p.add_argument('--output',type=Path,default='result')\n"
                " p.add_argument('--label',type=str,default='unchanged')\n"
                " p.add_argument('--optional',type=int,default=argparse.SUPPRESS)\n"
                " return p\n"
                "if __name__=='__main__': print(json.dumps(vars(parser().parse_args()),default=str))\n")
            with patch.dict(os.environ):
                os.environ.pop("PYTHONPATH", None)
                direct = subprocess.run([sys.executable, "-m", "qec.benchmark.ququart_battery.cli"],
                                        cwd=root, check=True, capture_output=True, text=True)
                with runtime({"qec": {"enabled": True, "python": sys.executable, "cwd": directory}}) as instance:
                    connection = next(c for c in instance.connections if c["id"] == "qec")
                    self.assertEqual(connection["status"], "available", connection)
                    action = instance.actions["qec.ququart.benchmark"]
                    defaults = {f["name"]: f["default"] for f in action.fields if "default" in f}
                    self.assertEqual(defaults, json_loads(direct.stdout))
                    self.assertIs(type(defaults["trials"]), int)
                    self.assertIs(type(defaults["rate"]), float)
                    self.assertEqual(action.backend["module_path"], str(module))
                    job = instance.start(action.id, {})
                    record = instance.wait(job["id"])
                    self.assertEqual(record["status"], "succeeded", record)
                    self.assertEqual(record["result"], json_loads(direct.stdout))

    def test_ollama_generation_relies_on_shared_deadline_not_socket_timeout(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.readline.side_effect = [b'{"response":"done","done":true}\n']
        opener = MagicMock()
        opener.open.return_value = response
        params = {"model": "fixture", "prompt": "Hi", "temperature": .7, "seed": 42}
        with patch("qsol_workbench.worker.urllib.request.build_opener", return_value=opener), patch("sys.stdin", io.StringIO(json.dumps(params))), redirect_stdout(io.StringIO()) as output:
            inference("ollama-generate", "http://127.0.0.1:11434")
        self.assertIsNone(opener.open.call_args.kwargs["timeout"])
        self.assertTrue(json_loads(output.getvalue())["done"])

    def test_blocked_ollama_worker_is_stopped_by_shared_run_deadline(self):
        requested = threading.Event()
        release = threading.Event()
        class Ollama(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"models":[{"name":"fixture"}]}')
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                requested.set()
                release.wait(timeout=3)
                try:
                    self.send_response(200); self.end_headers()
                    self.wfile.write(b'{"response":"late","done":true}\n')
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with runtime({"ollama": {"enabled": True, "url": f"http://127.0.0.1:{server.server_port}"}}, timeout=1) as instance:
                job = instance.start("inference.generate", {"prompt": "Hi"})
                self.assertTrue(requested.wait(timeout=2))
                started = time.monotonic()
                record = instance.wait(job["id"])
                self.assertEqual(record["status"], "timed_out")
                self.assertEqual(record["transport_status"], "timed_out")
                self.assertLess(time.monotonic() - started, 2)
        finally:
            release.set()
            server.shutdown(); server.server_close(); thread.join()

    def test_qec_discovers_new_argument_and_executes_it_without_ui_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "qec/benchmark/ququart_battery/cli.py"
            module.parent.mkdir(parents=True)
            for parent in [root / "qec", root / "qec/benchmark", module.parent]:
                (parent / "__init__.py").write_text("")
            base = "import argparse,json\ndef parser():\n p=argparse.ArgumentParser()\n p.add_argument('--trials',type=int,default=5)\n{extra} return p\nif __name__=='__main__': print(json.dumps(vars(parser().parse_args())))\n"
            module.write_text(base.format(extra=""))
            config = {"qec": {"enabled": True, "python": sys.executable, "cwd": directory}}
            with patch.dict(os.environ, {"PYTHONPATH": directory}):
                with runtime(config) as instance:
                    old = instance.actions["qec.ququart.benchmark"].public()
                    module.write_text(base.format(extra=" p.add_argument('--new-knob',type=float,default=0.25)\n"))
                    refreshed = instance.refresh()
                    action = next(a for a in refreshed["actions"] if a["id"] == "qec.ququart.benchmark")
                    self.assertIn("new_knob", [f["name"] for f in action["fields"]])
                    self.assertNotEqual(old["schema_sha256"], action["schema_sha256"])
                    job = instance.start(action["id"], {"trials": 2, "new_knob": .75}, action["schema_sha256"])
                    record = instance.wait(job["id"])
                    self.assertEqual(record["status"], "succeeded", record)
                    self.assertEqual(record["result"]["new_knob"], .75)

    def test_control_protocol_fixture(self):
        program = "import sys,json; r=json.loads(sys.stdin.readline()); print(json.dumps({'protocol':'qsol-control-agent-response/1','request_id':r['request_id'],'operation':r['operation'],'ok':True,'authority':'orchestration-only','result':{'available':True}}))"
        with runtime({"control": {"enabled": True, "argv": [sys.executable, "-c", program]}}) as instance:
            job = instance.start("control.health", {})
            record = instance.wait(job["id"])
            self.assertEqual(record["status"], "succeeded", record)
            self.assertTrue(record["result"]["result"]["available"])

    def test_inference_stream_against_local_http_fixture(self):
        class Ollama(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"models":[{"name":"fixture-model"}]}')
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.server.seen = body
                self.send_response(200); self.end_headers()
                self.wfile.write(b'{"response":"Hello ","done":false}\n{"response":"world","done":true,"eval_count":2}\n')
        server = ThreadingHTTPServer(("127.0.0.1", 0), Ollama)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with runtime({"ollama": {"enabled": True, "url": f"http://127.0.0.1:{server.server_port}"}}) as instance:
                job = instance.start("inference.generate", {"prompt": "Hi"})
                record = instance.wait(job["id"])
                self.assertEqual(record["status"], "succeeded", record)
                self.assertEqual(record["result"]["text"], "Hello world")
                self.assertEqual(server.seen["prompt"], "Hi")
        finally:
            server.shutdown(); server.server_close(); thread.join()


class WebTests(unittest.TestCase):
    def test_absolute_form_api_requests_require_the_same_authentication(self):
        with runtime() as instance:
            job = instance.start("demo.experiment", {"label": "private prompt", "delay": 0})
            instance.wait(job["id"])
            server = make_server(instance, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            host = f"127.0.0.1:{server.server_port}"
            def request(method, target, token=None, body=None):
                connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                headers = {"Host": host}
                if token is not None:
                    headers["Authorization"] = "Bearer " + token
                if body is not None:
                    headers["Content-Type"] = "application/json"
                    body = json.dumps(body)
                try:
                    connection.request(method, target, body=body, headers=headers)
                    response = connection.getresponse()
                    return response.status, response.read()
                finally:
                    connection.close()
            try:
                for path in ("/api/manifest", "/api/runs", "/api/runs/" + job["id"]):
                    for target in (path, "http://" + host + path):
                        for token in (None, "wrong"):
                            with self.subTest(target=target, authenticated=False):
                                status, data = request("GET", target, token)
                                self.assertEqual(status, 401)
                                self.assertNotIn(b"private prompt", data)
                        status, data = request("GET", target, server.workbench_token)
                        self.assertEqual(status, 200)
                        self.assertIsNotNone(json_loads(data))
                payload = {"action": "demo.experiment", "parameters": {"delay": 0}}
                for target in ("/api/run", "http://" + host + "/api/run"):
                    status, _ = request("POST", target, body=payload)
                    self.assertEqual(status, 401)
                self.assertEqual(len(instance.jobs), 1)
                status, data = request("POST", "http://" + host + "/api/run", server.workbench_token, payload)
                self.assertEqual(status, 202)
                self.assertEqual(instance.wait(json_loads(data)["id"])["status"], "succeeded")
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_persistence_encoding_error_remains_inspectable_over_http(self):
        with runtime() as instance:
            instance.actions["demo.experiment"].build = lambda p: Plan(
                [sys.executable, "-c", "print(" + repr('{"text":"\\ud800"}') + ")"])
            job = instance.start("demo.experiment", {})
            result = instance.wait(job["id"])
            self.assertIn("persistence_error", result)
            server = make_server(instance, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/runs/{job['id']}",
                    headers={"Authorization": "Bearer " + server.workbench_token})
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(json_loads(response.read()), result)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_authenticated_http_uses_shared_runtime(self):
        with runtime() as instance:
            server = make_server(instance, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            origin = f"http://127.0.0.1:{server.server_port}"
            def request(path, body=None, token=True, headers=None):
                extra = {"Content-Type": "application/json", **(headers or {})}
                if token: extra["Authorization"] = "Bearer " + server.workbench_token
                req = urllib.request.Request(origin + path, headers=extra,
                      data=None if body is None else json.dumps(body).encode())
                with urllib.request.urlopen(req, timeout=5) as response:
                    return json.loads(response.read())
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/manifest", token=False)
                self.assertEqual(error.exception.code, 401)
                error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/run", {}, headers={"Origin": "https://unrelated.invalid"})
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/manifest", headers={"Host": "attacker.invalid"})
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                manifest = request("/api/manifest")
                action = manifest["actions"][0]
                job = request("/api/run", {"action": action["id"], "parameters": {"delay": 0},
                                           "schema_sha256": action["schema_sha256"]})
                instance.wait(job["id"])
                record = request("/api/runs/" + job["id"])
                self.assertEqual(record["result"]["total"], 105)
                self.assertEqual(len(request("/api/runs")), 1)
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    unittest.main()
