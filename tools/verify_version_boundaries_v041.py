from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PHASE2_EVIDENCE_SHA256 = "594b173b413668416cf73c25a0f08080b98de1069008ffc9562fb237f935a942"
V040_RELEASE_JSON_SHA256 = "aa4b89e23a46f7e09060be00ead7be33965dff788d2792daf2258f1222d19ad2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def classification_semantics(profile: dict[str, Any]) -> dict[str, Any]:
    document = {key: value for key, value in profile.items() if key != "expected_fields_by_category"}
    document["rules"] = [
        {key: value for key, value in rule.items() if key != "expected_fields"}
        for rule in profile["rules"]
    ]
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v040", type=Path, required=True)
    parser.add_argument("--v041", type=Path, required=True)
    parser.add_argument("--v040-release-json", type=Path, required=True)
    parser.add_argument("--phase2-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks: dict[str, Any] = {
        "phase2_evidence_unchanged": sha256(args.phase2_evidence) == PHASE2_EVIDENCE_SHA256,
        "v040_release_record_unchanged": sha256(args.v040_release_json) == V040_RELEASE_JSON_SHA256,
        "classifier_source_unchanged": sha256(args.v040 / "src/osm_scientific_converter/core/classifier.py") == sha256(args.v041 / "src/osm_scientific_converter/core/classifier.py"),
        "rule_engine_source_unchanged": sha256(args.v040 / "src/osm_scientific_converter/core/rules.py") == sha256(args.v041 / "src/osm_scientific_converter/core/rules.py"),
        "scanner_source_unchanged": sha256(args.v040 / "src/osm_scientific_converter/core/scanner.py") == sha256(args.v041 / "src/osm_scientific_converter/core/scanner.py"),
    }
    profiles: dict[str, Any] = {}
    for topic in ("power", "pipeline", "aeroway"):
        old_path = args.v040 / f"src/osm_scientific_converter/resources/profiles/{topic}.json"
        new_path = args.v041 / f"src/osm_scientific_converter/resources/profiles/{topic}.json"
        old = load(old_path)
        new = load(new_path)
        profiles[topic] = {
            "v040_sha256": sha256(old_path),
            "v041_sha256": sha256(new_path),
            "hash_changed": sha256(old_path) != sha256(new_path),
            "classification_semantics_equal_after_removing_expected_field_metadata": classification_semantics(old) == classification_semantics(new),
        }
    checks["all_profile_classification_semantics_unchanged"] = all(item["classification_semantics_equal_after_removing_expected_field_metadata"] for item in profiles.values())
    checks["all_v041_profile_hashes_changed"] = all(item["hash_changed"] for item in profiles.values())
    report = {
        "schema_version": "1.0",
        "decision": "v0.4.1 is derived only from frozen v0.4.0; Phase 1 v0.2.3 and Phase 2 v0.3.1 remain external frozen predecessors.",
        "checks": checks,
        "profiles": profiles,
        "allowed_v041_differences": [
            "export field subset enforcement",
            "deterministic stratified quality sampling",
            "category-applicable expected field metadata",
            "advanced JSON GUI validation",
            "persistent paginated selections",
            "v0.4.1 user/release materials",
        ],
        "status": "success" if all(bool(value) for value in checks.values()) else "failed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks)}, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
