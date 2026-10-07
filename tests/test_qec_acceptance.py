"""Offline evidence regressions; real execution belongs to p1-qec.yml."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qec_acceptance import (compare_reports, qec_digest, read_json, seal,
                            sha256, verify_artifacts, verify_evidence, write_json)

EVIDENCE = ROOT / "evidence/p1-qec"


class QecEvidenceTests(unittest.TestCase):
    def test_retained_real_qec_gate_verifies_without_qec_or_browser(self):
        result = verify_evidence(EVIDENCE)
        self.assertTrue(result["byte_identical"])
        self.assertEqual(result["artifact_count_per_mode"], 15)
        self.assertEqual(result["normalized_fields"], [])

    def test_changed_or_missing_scientific_artifact_is_rejected(self):
        for operation in ("change", "remove"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "report"
                shutil.copytree(EVIDENCE / "artifacts/direct", report)
                artifact = report / "monte_carlo_fer.csv"
                if operation == "remove":
                    artifact.unlink()
                else:
                    artifact.write_bytes(artifact.read_bytes() + b"changed\n")
                with self.assertRaisesRegex(ValueError, "missing|checksum"):
                    verify_artifacts(report)

    def test_rehashed_but_different_scientific_output_cannot_pass_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "changed"
            shutil.copytree(EVIDENCE / "artifacts/direct", changed)
            artifact = changed / "monte_carlo_fer.csv"
            # Valid CSV with altered numeric evidence, consistently rehashed.
            lines = artifact.read_text().splitlines()
            cells = lines[1].split(",")
            cells[-1] = "0.999999999"
            lines[1] = ",".join(cells)
            artifact.write_text("\n".join(lines) + "\n")
            manifest = read_json(changed / "benchmark_manifest.json")
            manifest["files"][artifact.name] = sha256(artifact)
            manifest.pop("sha256")
            manifest["sha256"] = qec_digest(manifest)
            write_json(changed / "benchmark_manifest.json", manifest)
            verify_artifacts(changed)
            with self.assertRaisesRegex(ValueError, "artifacts differ"):
                compare_reports([EVIDENCE / "artifacts/direct", changed])

    def test_methodology_must_match_requested_trials_and_rates(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report"
            shutil.copytree(EVIDENCE / "artifacts/direct", report)
            methodology = read_json(report / "methodology.json")
            methodology["monte_carlo"]["trials_per_cell"] += 1
            methodology.pop("sha256")
            methodology["sha256"] = qec_digest(methodology)
            write_json(report / "methodology.json", methodology)
            manifest = read_json(report / "benchmark_manifest.json")
            manifest["methodology_sha256"] = methodology["sha256"]
            manifest["files"]["methodology.json"] = sha256(report / "methodology.json")
            manifest.pop("sha256")
            manifest["sha256"] = qec_digest(manifest)
            write_json(report / "benchmark_manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "requested inputs"):
                verify_artifacts(report)

    def test_resealed_outcome_and_identity_mutations_fail_closed(self):
        changes = [
            ("validation/direct.json", lambda value: value.update(passed=False)),
            ("commands/validate-cli.json", lambda value: value.update(exit_code=1)),
            ("commands/cli-failure.json", lambda value: value.update(exit_code=0)),
            ("commands/validate-negative.json", lambda value: value.update(exit_code=0)),
            ("browser.json", lambda value: value.update(engine="Node DOM fixture")),
            ("browser.json", lambda value: value["runs"][0].update(id="0" * 32)),
            ("qec-source.json", lambda value: value.update(commit="0" * 40)),
            ("environment.json", lambda value: value["packages"]["numpy"].update(version="0.0")),
            ("summary.json", lambda value: value.update(comparison={"byte_identical": True})),
        ]
        for name, mutate in changes:
            with self.subTest(file=name), tempfile.TemporaryDirectory() as directory:
                evidence = Path(directory) / "evidence"
                shutil.copytree(EVIDENCE, evidence)
                value = deepcopy(read_json(evidence / name))
                mutate(value)
                write_json(evidence / name, value)
                seal(evidence)
                with self.assertRaises(ValueError):
                    verify_evidence(evidence)

    def test_evidence_inventory_requires_every_retained_file(self):
        for name in ("unlisted.txt", "commands/SHA256SUMS"):
            with self.subTest(file=name), tempfile.TemporaryDirectory() as directory:
                evidence = Path(directory) / "evidence"
                shutil.copytree(EVIDENCE, evidence)
                (evidence / name).write_text("unlisted")
                with self.assertRaisesRegex(ValueError, "Incomplete"):
                    verify_evidence(evidence)


if __name__ == "__main__":
    unittest.main()
