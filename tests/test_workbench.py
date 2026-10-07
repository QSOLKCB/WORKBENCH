"""Behavior and integration-contract tests; no model or QEC install required."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
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
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qsol_workbench.adapters.builtin import check_control
from qsol_workbench.model import Plan, digest, field, json_loads, validate
from qsol_workbench.process import execute
from qsol_workbench.runtime import Runtime
from qsol_workbench.web import make_server


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
