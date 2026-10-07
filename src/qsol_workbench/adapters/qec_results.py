"""Structural checks for the three reviewed QEC JSON output versions.

Hashes here check the returned object; artifact bytes and scientific claims
remain QEC's responsibility. No scientific modules are imported.
"""
import re

from ..model import digest

QUQUART = "qec.ququart-fer-battery.v170.1.1"
QUTRIT = "qec.qutrit-decoder-benchmark.v1"
RECEIPT = "qec.ququart-report-claim-validation.v1"
ARTIFACTS = {
    QUQUART: {
        "exact_weight_enumerator.csv", "exact_fer_curve.csv", "exact_channel_weight_enumerator.csv",
        "exact_channel_fer.csv", "monte_carlo_fer.csv", "harmonic_fault_matrix.csv", "harmonic_end_to_end.csv",
        "receiver_operating_curve.csv", "lane_symmetry_certificate.json", "report_claims.json",
        "claim_validation.json", "qbraid_replication_receipt.json", "methodology.json", "report.js",
    },
    QUTRIT: {
        "decoded_logical_error_long.csv", "decoded_logical_error_wide.csv", "guaranteed_radius_tail_long.csv",
        "guaranteed_radius_tail_wide.csv", "deterministic_stress_corpus.csv", "harmonic_fault_injection.csv",
        "v3_overlay.csv", "v3_numeric_deltas.csv", "published_evidence.csv", "research_watch.csv",
        "historical_v3_baseline.csv", "methodology.json",
    },
}
HASH_FIELDS = {
    QUQUART: {"methodology_sha256", "lane_symmetry_sha256", "replication_receipt_sha256",
              "claim_validation_sha256", "v170_0_certificate_sha256"},
    QUTRIT: {"methodology_sha256", "historical_v3_sha256"},
    RECEIPT: {"claims_sha256", "facts_sha256"},
}
CHECKS = {"numeric_claims_match", "false_accept_claims_match", "lane_symmetry_claim_matches",
          "threshold_claim_permitted", "controlled_curve_language", "test_claim_requires_receipt",
          "artifact_matches_require_full_sha256", "hardware_contract_enforced"}


def require(condition, message):
    if not condition:
        raise ValueError("QEC result contract error: " + message)


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_result(result, schema):
    require(schema in HASH_FIELDS and isinstance(result, dict) and result.get("schema") == schema,
            "unsupported output schema")
    for name in HASH_FIELDS[schema] | {"sha256"}:
        require(valid_hash(result.get(name)), "missing or invalid " + name)
    if schema in ARTIFACTS:
        files = result.get("files")
        require(isinstance(files, dict) and set(files) == ARTIFACTS[schema], "incomplete artifact files object")
        require(all(valid_hash(value) for value in files.values()), "invalid artifact hash")
        require(result.get("deterministic") is True, "manifest must declare deterministic output")
        if schema == QUQUART:
            require(result.get("version") == "170.1.1" and type(result.get("seed")) is int,
                    "invalid manifest version or seed")
    else:
        require(result.get("passed") is True, "receipt must report successful validation")
        checks = result.get("checks")
        require(isinstance(checks, dict) and set(checks) == CHECKS and
                all(type(value) is bool for value in checks.values()), "incomplete or invalid receipt checks")
        require(all(value is (name != "threshold_claim_permitted") for name, value in checks.items()),
                "receipt checks contradict successful validation")
    payload = {key: value for key, value in result.items() if key != "sha256"}
    require(result["sha256"] == digest(payload), "result checksum mismatch")
