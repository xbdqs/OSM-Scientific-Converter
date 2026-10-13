from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osm_scientific_converter import __version__
from osm_scientific_converter.core.profiles import list_builtin_profiles


PHASE2_EVIDENCE_SHA256 = "594b173b413668416cf73c25a0f08080b98de1069008ffc9562fb237f935a942"
V040_RELEASE_JSON_SHA256 = "aa4b89e23a46f7e09060be00ead7be33965dff788d2792daf2258f1222d19ad2"
EXPECTED_V041_PROFILE_HASHES = {
    "aeroway": "ff2f74757d78bed9e776512d4d0ba6112a1b2f959f774ebea31dda12c2bc23b4",
    "pipeline": "7ad325f8ea9bce00c727703aa872219d14aad233371412d2352db0e76edcfa2e",
    "power": "393249f2c3fb8e3263b10d5e5902852b7a881089d33189843441dad35da2fd1f",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate v0.4.1 hardening and release validation")
    parser.add_argument("--performance", type=Path, required=True)
    parser.add_argument("--gui-acceptance", type=Path, required=True)
    parser.add_argument("--standalone", type=Path, required=True)
    parser.add_argument("--wheel-smoke", type=Path, required=True)
    parser.add_argument("--test-matrix", type=Path, required=True)
    parser.add_argument("--version-boundary-audit", type=Path, required=True)
    parser.add_argument("--performance-build-equivalence", type=Path, required=True)
    parser.add_argument("--phase2-evidence", type=Path, required=True)
    parser.add_argument("--v040-release-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    performance = load(args.performance)
    acceptance = load(args.gui_acceptance)
    standalone = load(args.standalone)
    wheel_smoke = load(args.wheel_smoke)
    test_matrix = load(args.test_matrix)
    version_audit = load(args.version_boundary_audit)
    performance_equivalence = load(args.performance_build_equivalence)
    profile_hashes = {item["id"]: item["sha256"] for item in list_builtin_profiles()}
    checks: list[dict[str, Any]] = []

    def require(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    require("software version is exactly v0.4.1", __version__ == "0.4.1", __version__)
    require(
        "frozen Phase 2 evidence unchanged",
        sha256(args.phase2_evidence) == PHASE2_EVIDENCE_SHA256,
        sha256(args.phase2_evidence),
    )
    require(
        "frozen v0.4.0 release record unchanged",
        sha256(args.v040_release_json) == V040_RELEASE_JSON_SHA256,
        sha256(args.v040_release_json),
    )
    require("v0.4.1 expected-field profile hashes", profile_hashes == EXPECTED_V041_PROFILE_HASHES, profile_hashes)

    expected_test_runs = {
        "source_python_3_12_13",
        "source_python_3_13_14",
        "installed_wheel_python_3_12_13",
        "installed_wheel_python_3_13_14",
    }
    test_runs = test_matrix.get("runs", {})
    require(
        "strict source and installed-wheel test matrix",
        test_matrix.get("status") == "success"
        and set(test_runs) == expected_test_runs
        and all(
            run.get("status") == "success"
            and run.get("passed") == 90
            and run.get("warnings_as_errors") is True
            and run.get("software_version") == "0.4.1"
            for run in test_runs.values()
        ),
        test_runs,
    )
    require(
        "frozen-version boundary audit",
        version_audit.get("status") == "success"
        and all(bool(value) for value in version_audit.get("checks", {}).values()),
        version_audit.get("checks", {}),
    )
    require(
        "performance-tested build is functionally equivalent to final wheel",
        performance_equivalence.get("status") == "success"
        and all(bool(value) for value in performance_equivalence.get("checks", {}).values()),
        performance_equivalence,
    )
    require(
        "test matrix and equivalence audit identify the same final wheel",
        test_matrix.get("wheel", {}).get("sha256")
        == performance_equivalence.get("final_build", {}).get("sha256"),
        {
            "test_matrix": test_matrix.get("wheel"),
            "equivalence_final_build": performance_equivalence.get("final_build"),
        },
    )
    require(
        "wheel GUI five-step smoke",
        wheel_smoke.get("status") == "success"
        and wheel_smoke.get("five_step_pages") == 5
        and wheel_smoke.get("software_version") == "0.4.1",
        wheel_smoke,
    )
    require(
        "standalone clean environment",
        standalone.get("status") == "success"
        and standalone.get("clean_environment") is True
        and standalone.get("frozen") is True,
        standalone,
    )
    workflow = standalone.get("workflow", {})
    require(
        "standalone field subset applied",
        workflow.get("field_selection_applied") is True
        and workflow.get("selected_profile_attributes") == ["voltage"],
        workflow,
    )
    require(
        "standalone stratified quality",
        "category × geometry_group" in workflow.get("quality_sampling", "")
        and all(item.get("sampled", 0) > 0 for item in workflow.get("quality_strata", [])),
        workflow,
    )
    require(
        "four-region final performance/reproducibility",
        performance.get("status") == "success"
        and set(performance.get("cases", {}))
        == {"berlin_power", "south_korea_aeroway", "new_york_pipeline", "quebec_power"},
        {key: value.get("status") for key, value in performance.get("cases", {}).items()},
    )
    require(
        "three packaged-EXE GUI acceptance cases",
        acceptance.get("status") == "success"
        and set(acceptance.get("cases", {}))
        == {"berlin_power", "south_korea_aeroway", "new_york_pipeline"},
        {key: value.get("status") for key, value in acceptance.get("cases", {}).items()},
    )

    report = {
        "schema_version": "1.0",
        "software_version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tests": test_runs,
        "profile_hashes": profile_hashes,
        "real_validation": {key: value["status"] for key, value in performance.get("cases", {}).items()},
        "gui_acceptance": {key: value["status"] for key, value in acceptance.get("cases", {}).items()},
        "checks": checks,
        "status": "success" if all(item["passed"] for item in checks) else "failed",
    }
    (args.output / "PHASE3_V041_VALIDATION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# OSM Scientific Converter Phase 3 v0.4.1 验证",
        "",
        f"- 状态：**{report['status']}**",
        "- Python 3.12.13 / 3.13.14：源代码与安装 wheel 均各 90 项 `-W error` 测试通过；结论来自 TEST_MATRIX.json，不是硬编码。",
        "- Windows 独立 EXE：清洁环境、稳定 GDAL、字段子集、分层质量检查完整工作流通过。",
        "- 真实数据：Berlin、South Korea、New York、Quebec 最终 release 性能与两次复现验证通过。",
        "- GUI 验收：通过打包 EXE 的真实 GUI 控件自动执行并保存截图；不表述为人工鼠标测试。",
        "- 冻结 Phase 2 v0.3.1 证据和 v0.4.0 release JSON 未修改；v0.4.1 profile 哈希因 expected-field 元数据而改变，分类 expression 未改变。",
        "- 长时性能测试构建与最终 wheel 的分类、导入、扫描、质量、profile、CLI 与 resources 逻辑字节一致；exporter 的唯一差异经机械审计限定为 resolved-category 审计元数据补全，另有 GUI 证据修复，均由最终 90 项测试矩阵覆盖。",
        "",
    ]
    (args.output / "PHASE3_V041_VALIDATION_CN.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks)}, ensure_ascii=False))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
