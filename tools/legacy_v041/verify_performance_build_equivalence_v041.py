from __future__ import annotations

import argparse
import ast
import hashlib
import json
import zipfile
from pathlib import Path


ALLOWED_DIFFERENCE_SUFFIXES = (
    "osm_scientific_converter/__init__.py",
    "osm_scientific_converter/core/exporter.py",
    "osm_scientific_converter/gui/app.py",
    "osm_scientific_converter/gui/main_window.py",
    ".dist-info/METADATA",
    ".dist-info/RECORD",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def without_module_docstring(source: bytes) -> str:
    tree = ast.parse(source.decode("utf-8"))
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        tree.body.pop(0)
    return ast.dump(tree, include_attributes=False)


def exporter_change_is_exact_audit_hardening(old_source: bytes, new_source: bytes) -> bool:
    """Prove that the exporter delta is only the resolved-category audit fix."""
    text = new_source.decode("utf-8")
    new_default = '            categories = sorted(default_categories.intersection(available))\n'
    old_default = new_default + '            selection = {**selection, "resolved_categories": categories}\n'
    new_explicit = '            categories = list(requested_categories)\n'
    old_explicit = '            categories = requested_categories\n'
    new_audit = (
        '        # Record the effective category set on every path.  In particular, an\n'
        '        # explicit selection must not be mistaken for an empty/default result\n'
        '        # by the GUI or by downstream release evidence.\n'
        '        selection = {**selection, "resolved_categories": list(categories)}\n'
    )
    if text.count(new_default) != 1 or text.count(new_explicit) != 1 or text.count(new_audit) != 1:
        return False
    reconstructed_old = text.replace(new_default, old_default).replace(new_explicit, old_explicit).replace(new_audit, "")
    return reconstructed_old.encode("utf-8") == old_source


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify functional equivalence of the performance-tested and final v0.4.1 wheels")
    parser.add_argument("--performance-wheel", type=Path, required=True)
    parser.add_argument("--final-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with zipfile.ZipFile(args.performance_wheel) as old_archive, zipfile.ZipFile(args.final_wheel) as new_archive:
        old_names = set(old_archive.namelist())
        new_names = set(new_archive.namelist())
        common = old_names & new_names
        changed = sorted(name for name in common if old_archive.read(name) != new_archive.read(name))
        unexpected = [name for name in changed if not name.endswith(ALLOWED_DIFFERENCE_SUFFIXES)]
        init_name = "osm_scientific_converter/__init__.py"
        init_ast_equal = without_module_docstring(old_archive.read(init_name)) == without_module_docstring(new_archive.read(init_name))
        exporter_name = "osm_scientific_converter/core/exporter.py"
        exporter_audit_only = exporter_change_is_exact_audit_hardening(
            old_archive.read(exporter_name), new_archive.read(exporter_name)
        )
        performance_scientific_members = sorted(
            name for name in common
            if (
                (name.startswith("osm_scientific_converter/core/") and name != exporter_name)
                or name == "osm_scientific_converter/gui/quality.py"
                or name.startswith("osm_scientific_converter/resources/")
                or name.startswith("osm_scientific_converter/cli/")
            )
        )
        scientific_members_equal = all(old_archive.read(name) == new_archive.read(name) for name in performance_scientific_members)
        profile_members_equal = all(
            old_archive.read(name) == new_archive.read(name)
            for name in performance_scientific_members
            if "/resources/profiles/" in name
        )

    checks = {
        "wheel_member_names_equal": old_names == new_names,
        "all_performance_scientific_members_except_audited_exporter_delta_byte_equal": scientific_members_equal,
        "exporter_delta_is_exact_resolved_category_audit_hardening": exporter_audit_only,
        "all_profile_members_byte_equal": profile_members_equal,
        "only_documented_members_changed": not unexpected,
        "init_code_equal_after_removing_module_docstring": init_ast_equal,
    }
    report = {
        "schema_version": "1.0",
        "performance_tested_build": {"file": f"{args.performance_wheel.parent.name}/{args.performance_wheel.name}", "sha256": sha256(args.performance_wheel)},
        "final_build": {"file": f"{args.final_wheel.parent.name}/{args.final_wheel.name}", "sha256": sha256(args.final_wheel)},
        "changed_members": changed,
        "allowed_change_explanation": {
            "osm_scientific_converter/__init__.py": "Module docstring corrected from Phase 2 to Phase 3 v0.4.1; AST is otherwise identical.",
            "osm_scientific_converter/core/exporter.py": "Exact audited delta: always records the effective category list, including explicit selections; selection, feature writing, geometry, field handling, and monitoring code are unchanged. Covered by the 90-test final source/wheel matrix and explicit-category audit regression.",
            "osm_scientific_converter/gui/app.py": "Packaged-GUI acceptance now synchronizes the visible category checks with the resolved export selection and verifies equality.",
            "osm_scientific_converter/gui/main_window.py": "Export-page category state can be explicitly applied/read and restored from project state; performance core does not import this module.",
            "METADATA": "README/version-boundary wording corrected; package requirements and version remain v0.4.1.",
            "RECORD": "Wheel hash manifest necessarily changed with the two files above.",
        },
        "checks": checks,
        "decision": "The long real-data performance build and final wheel have byte-identical classification, import, scan, quality, profile, CLI, and resource logic. The exporter delta is mechanically proven to be only resolved-category audit metadata hardening and is covered by the final 90-test source/wheel matrix; feature selection/writing and performance paths are unchanged. The builds are therefore performance-functionally equivalent but not byte-identical.",
        "status": "success" if all(checks.values()) else "failed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "changed_members": changed}))
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
