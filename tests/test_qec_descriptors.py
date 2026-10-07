"""Backend descriptor fixtures; real QEC parity has its own acceptance job."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from qsol_workbench.adapters.qec_descriptor import COMMANDS
from qsol_workbench.runtime import Runtime
from qsol_workbench.web import make_server


def scalar(name, kind="string", **values):
    return {"name": name, "type": kind, "flag": "--" + name.replace("_", "-"),
            "label": name.title(), "required": False, **values}


def fixture_descriptor():
    actions = []
    for action_id, (module, schema, view) in COMMANDS.items():
        fields = [scalar("output", path_role="write-directory", path_base="cwd", default="result")]
        output = {"format": "json", "schema": schema, "view": view, "directory_field": "output"}
        if view == "validation-receipt":
            fields = [scalar("claims", required=True, path_role="read-file", path_base="cwd"),
                      scalar("evidence", required=True, path_role="read-directory", path_base="cwd")]
            output = {"format": "json", "schema": schema, "view": view, "success_field": "passed"}
        actions.append({"id": action_id, "module": module, "title": action_id, "description": "fixture",
                        "fields": fields, "effect": "writes-artifacts", "output": output})
    return {"protocol": "qec-capabilities/1", "implementation_modules": ["qec.capabilities"], "actions": actions}


@contextmanager
def backend(descriptor=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        qec = root / "qec"
        qec.mkdir(); (qec / "__init__.py").write_text("")
        # Valid result shapes captured from the pinned backend; these remain
        # fixtures, not evidence that this temporary backend ran science.
        result_paths = ("artifacts/direct/ququart/benchmark_manifest.json", "validation/direct.json",
                        "artifacts/direct/qutrit/benchmark_manifest.json")
        results = {action: json.loads((ROOT / "evidence/p2-qec" / path).read_text())
                   for action, path in zip(COMMANDS, result_paths)}
        data = {"descriptor": deepcopy(descriptor or fixture_descriptor()), "responses": {}, "results": results}
        def publish():
            (root / "descriptor.json").write_text(json.dumps(data))
        publish()
        (qec / "capabilities.py").write_text(
            "import json\nfrom pathlib import Path\n"
            "def descriptor(): return json.loads((Path(__file__).parent.parent/'descriptor.json').read_text())['descriptor']\n")
        program = """import argparse,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[3]
(root/'cli-imported').write_text('imported')
data=json.loads((root/'descriptor.json').read_text())
action=next(action for action in data['descriptor']['actions'] if action['module']==__spec__.name)
parser=argparse.ArgumentParser()
for field in action['fields']:
 kind=field['type']
 converter={'string':str,'integer':int,'number':float,'boolean':lambda value:value=='true'}[kind]
 parser.add_argument(field['flag'],type=converter,required=field.get('required',False),
                     default=field.get('default',argparse.SUPPRESS),choices=field.get('choices'))
if __name__=='__main__':
 params=vars(parser.parse_args())
 result=data['results'][action['id']]
 result['parameters']=params
 result.update(data['responses'].get(action['id'],{}))
 result.pop('sha256',None)
 result['sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 if 'sha256' in data['responses'].get(action['id'],{}): result['sha256']=data['responses'][action['id']]['sha256']
 print(json.dumps(result))
"""
        for module, _, _ in COMMANDS.values():
            path = root.joinpath(*module.split(".")).with_suffix(".py")
            path.parent.mkdir(parents=True, exist_ok=True)
            for parent in (qec / "benchmark", path.parent):
                (parent / "__init__.py").write_text("")
            path.write_text(program)
        config = {"demo": {"enabled": False}, "qec": {"enabled": True, "python": sys.executable, "cwd": str(root)}}
        with patch.dict(os.environ, {"PYTHONPATH": str(root)}):
            yield root, config, data, publish


class DescriptorTests(unittest.TestCase):
    def test_discovery_does_not_import_cli_and_exposes_three_operations(self):
        with backend() as (root, config, data, publish):
            instance = Runtime(config, root / "store")
            try:
                self.assertEqual(set(instance.actions), set(COMMANDS))
                self.assertFalse((root / "cli-imported").exists())
                manifest = instance.manifest()
                self.assertTrue(all(action["backend"]["discovery"] == "descriptor" for action in manifest["actions"]))
                self.assertTrue(all(action["output"]["format"] == "json" for action in manifest["actions"]))
            finally:
                instance.close()

    def test_supported_scalar_values_defaults_choices_and_paths_reach_direct_cli(self):
        descriptor = fixture_descriptor()
        descriptor["actions"][0]["fields"] += [
            scalar("count", "integer", default=2, minimum=1, maximum=3, choices=[1, 2, 3]),
            scalar("enabled", "boolean", default=False, choices=[True, False]),
            scalar("label", default="--literal")]
        with backend(descriptor) as (root, config, data, publish):
            instance = Runtime(config, root / "store")
            try:
                for supplied in ({}, {"count": 3, "enabled": True, "output": "relative output", "label": "-x; $(echo nope)"}):
                    action = instance.actions["qec.ququart.benchmark"]
                    job = instance.start(action.id, supplied)
                    record = instance.wait(job["id"])
                    self.assertEqual(record["status"], "succeeded", record)
                    direct = subprocess.run(record["execution"]["argv"], cwd=root, check=True, capture_output=True, text=True)
                    self.assertEqual(record["result"], json.loads(direct.stdout))
                    self.assertEqual(record["result"]["parameters"], record["parameters"])
                for supplied in ({"count": 0}, {"count": 4}, {"enabled": 1}):
                    with self.assertRaises(ValueError):
                        instance.start(action.id, supplied)
            finally:
                instance.close()

    def test_refresh_updates_http_and_cli_and_rejects_stale_fingerprint(self):
        with backend() as (root, config, data, publish):
            instance = Runtime(config, root / "store")
            server = make_server(instance, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            def request(path, body=None):
                headers = {"Authorization": "Bearer " + server.workbench_token, "Content-Type": "application/json"}
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}" + path,
                                                 data=None if body is None else json.dumps(body).encode(), headers=headers)
                with urllib.request.urlopen(request) as response:
                    return json.load(response)
            try:
                before = request("/api/manifest")["actions"][0]
                data["descriptor"]["actions"][0]["fields"].append(scalar("new_option", "integer", default=7, choices=[7, 9]))
                publish()
                refreshed = request("/api/refresh", {})["actions"][0]
                self.assertEqual(refreshed["fields"][-1]["name"], "new_option")
                self.assertNotEqual(refreshed["schema_sha256"], before["schema_sha256"])
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    request("/api/run", {"action": before["id"], "parameters": {}, "schema_sha256": before["schema_sha256"]})
                self.assertEqual(failure.exception.code, 400)
                self.assertEqual(len(instance.jobs), 0)
                job = request("/api/run", {"action": refreshed["id"], "parameters": {"new_option": 9}, "schema_sha256": refreshed["schema_sha256"]})
                record = instance.wait(job["id"])
                self.assertEqual(record["result"]["parameters"]["new_option"], 9)
                config_path = root / "config.json"; config_path.write_text(json.dumps(config))
                direct_cli = subprocess.run([sys.executable, str(ROOT / "workbench.py"), "--config", str(config_path),
                                             "--store", str(root / "cli-store"), "discover"], capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(direct_cli.stdout)["actions"][0]["fields"], refreshed["fields"])
            finally:
                server.shutdown(); server.server_close(); instance.close()

    def test_unsupported_protocol_shapes_commands_and_defaults_never_fall_back(self):
        mutations = [
            lambda value: value.update(protocol="qec-capabilities/2"),
            lambda value: value["actions"][0]["fields"][0].update(type="array"),
            lambda value: value["actions"][0]["fields"][0].update(nargs="+"),
            lambda value: value["actions"][0].update(module="qec.unreviewed"),
            lambda value: value["actions"][0]["fields"].append(scalar("count", "integer", default="bad")),
            lambda value: value["actions"][0]["fields"][0].update(path_base="browser"),
            lambda value: value["actions"].append(deepcopy(value["actions"][0])),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate), backend() as (root, config, data, publish):
                mutate(data["descriptor"]); publish()
                instance = Runtime(config, root / "store")
                try:
                    connection = next(c for c in instance.connections if c["id"] == "qec")
                    self.assertEqual(connection["status"], "unavailable", connection)
                    self.assertTrue(connection.get("reason"))
                    self.assertEqual(instance.actions, {})
                    self.assertFalse((root / "cli-imported").exists())
                finally:
                    instance.close()

    def test_required_validation_paths_and_all_entry_points_remain_distinct(self):
        with backend() as (root, config, data, publish):
            instance = Runtime(config, root / "store")
            try:
                with self.assertRaisesRegex(ValueError, "claims is required"):
                    instance.start("qec.ququart.validate", {})
                for action_id, (module, _, _) in COMMANDS.items():
                    params = {"claims": "a.json", "evidence": "relative"} if action_id == "qec.ququart.validate" else {}
                    record = instance.wait(instance.start(action_id, params)["id"])
                    self.assertEqual(record["status"], "succeeded", record)
                    self.assertEqual(record["execution"]["argv"][2], module)
                    self.assertEqual(record["result"]["parameters"], record["parameters"])
            finally:
                instance.close()

    def test_zero_exit_wrong_schema_and_unsuccessful_receipt_keep_transport_diagnostics(self):
        for response in ({"schema": "foreign/1"}, {"passed": False}):
            with self.subTest(response=response), backend() as (root, config, data, publish):
                data["responses"]["qec.ququart.validate"] = response; publish()
                instance = Runtime(config, root / "store")
                try:
                    record = instance.wait(instance.start("qec.ququart.validate", {"claims": "a", "evidence": "b"})["id"])
                    self.assertEqual(record["status"], "failed", record)
                    self.assertEqual(record["exit_code"], 0)
                    self.assertEqual(record["transport_status"], "succeeded")
                    self.assertTrue(record["stdout"])
                    self.assertTrue(record["error"])
                finally:
                    instance.close()

    def test_missing_descriptor_requires_explicit_legacy_mode(self):
        with backend() as (root, config, data, publish):
            (root / "qec/capabilities.py").unlink()
            instance = Runtime(config, root / "store")
            try:
                connection = next(c for c in instance.connections if c["id"] == "qec")
                self.assertEqual(connection["status"], "unavailable")
                self.assertIn("explicitly select discovery=legacy-argparse", connection["reason"])
            finally:
                instance.close()

    def test_zero_exit_incomplete_or_mistyped_results_never_persist_success(self):
        for action_id in COMMANDS:
            with self.subTest(action=action_id), backend() as (root, config, data, publish):
                instance = Runtime(config, root / "store")
                valid = deepcopy(data['results'][action_id])
                mutations = []
                # Every required top-level member, plus malformed nested data.
                for key in valid:
                    if key != 'sha256':
                        mutations.append(lambda result, key=key: result.pop(key))
                if 'files' in valid:
                    mutations += [lambda r: r.update(files=None), lambda r: r.update(files={}),
                                  lambda r: r['files'].update({'../foreign': '0' * 64}),
                                  lambda r: r['files'].update(methodology_json=123),
                                  lambda r: r['files'].update({'methodology.json': 'not-a-hash'}),
                                  lambda r: r.update(deterministic=1)]
                    if 'seed' in valid:
                        mutations.append(lambda r: r.update(seed=True))
                else:
                    mutations += [lambda r: r.update(checks=[]), lambda r: r.update(checks={}),
                                  lambda r: r['checks'].update(numeric_claims_match=1),
                                  lambda r: r['checks'].update(numeric_claims_match=False),
                                  lambda r: r['checks'].update(threshold_claim_permitted=True),
                                  lambda r: r.update(passed=1)]
                params = {'claims': 'a', 'evidence': 'b'} if action_id == 'qec.ququart.validate' else {}
                try:
                    for mutate in mutations:
                        data['results'][action_id] = deepcopy(valid)
                        mutate(data['results'][action_id]); publish()
                        record = instance.wait(instance.start(action_id, params)['id'])
                        self.assertEqual(record['status'], 'failed', record)
                        self.assertEqual(record['exit_code'], 0)
                        self.assertEqual(record['transport_status'], 'succeeded')
                        self.assertTrue(record['stdout'])
                        self.assertTrue(record['error'])
                        saved = json.loads((root / 'store' / (record['id'] + '.json')).read_text())
                        self.assertEqual(saved['status'], 'failed')
                    data['results'][action_id] = valid
                    data['responses'][action_id] = {'sha256': '0' * 64}; publish()
                    record = instance.wait(instance.start(action_id, params)['id'])
                    self.assertEqual(record['status'], 'failed')
                    self.assertIn('checksum mismatch', record['error'])
                finally:
                    instance.close()


if __name__ == "__main__":
    unittest.main()
