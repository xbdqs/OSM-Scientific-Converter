from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


VERSION = "0.4.1"
FIXED_TIME = (2026, 8, 4, 0, 0, 0)
PHASE2_EVIDENCE_SHA256 = "594b173b413668416cf73c25a0f08080b98de1069008ffc9562fb237f935a942"
V040_RELEASE_SHA256 = "aa4b89e23a46f7e09060be00ead7be33965dff788d2792daf2258f1222d19ad2"
USER_FILES = (
    "README_EN.md",
    "README_CN.md",
    "QUICK_START_CN.md",
    "LICENSE",
    "CITATION.cff",
    "THIRD_PARTY_NOTICES.md",
    "OSM_ATTRIBUTION_AND_ODBL.md",
    "CHANGELOG.md",
)
SOURCE_ROOT_FILES = (
    "README.md",
    *USER_FILES,
    "environment.yml",
    "PACKAGE_MANIFEST.json",
    "pyproject.toml",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name.replace("\\", "/"), FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def clean_source_files(root: Path) -> Iterable[Path]:
    for name in SOURCE_ROOT_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Required source material is missing: {path}")
        yield path
    for folder in ("config", "examples", "paper", "src", "tests", "tools"):
        current = root / folder
        for path in sorted(current.rglob("*")):
            lowered = [part.lower() for part in path.parts]
            if not path.is_file():
                continue
            if any(part == "__pycache__" or part.startswith(".pytest_cache") or part.endswith(".egg-info") for part in lowered):
                continue
            if path.suffix.lower() in {".pyc", ".pyo"} or "v040" in path.name.lower():
                continue
            yield path


def zip_directory(source: Path, output: Path, prefix: str) -> dict[str, object]:
    count = 0
    total = 0
    with zipfile.ZipFile(output, "w") as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            write_member(archive, f"{prefix}/{path.relative_to(source).as_posix()}", data)
            count += 1
            total += len(data)
    with zipfile.ZipFile(output) as archive:
        bad_crc = archive.testzip()
    if bad_crc:
        raise ValueError(f"ZIP CRC failure: {bad_crc}")
    return {"file": output.name, "sha256": sha256(output), "member_count": count, "uncompressed_bytes": total}


def copy_windows_user_materials(working: Path, windows_dir: Path) -> None:
    for name in USER_FILES:
        shutil.copy2(working / name, windows_dir / name)
    examples = windows_dir / "examples"
    examples.mkdir(exist_ok=True)
    for name in ("sample_infrastructure.osm", "expected_output_summary.json"):
        shutil.copy2(working / "examples" / name, examples / name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the single formal v0.4.1 artifact set")
    parser.add_argument("--working", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--windows-dir", type=Path, required=True)
    parser.add_argument("--phase2-evidence", type=Path, required=True)
    args = parser.parse_args()
    args.release.mkdir(parents=True, exist_ok=True)

    validation_json = args.validation / "PHASE3_V041_VALIDATION.json"
    validation = json.loads(validation_json.read_text(encoding="utf-8"))
    standalone_path = args.validation / "WINDOWS_STANDALONE_WORKFLOW_SMOKE.json"
    standalone = json.loads(standalone_path.read_text(encoding="utf-8"))
    wheel_smoke_path = args.validation / "WHEEL_GUI_SMOKE.json"
    wheel_smoke = json.loads(wheel_smoke_path.read_text(encoding="utf-8"))
    gui_acceptance_path = args.validation / "GUI_USER_ACCEPTANCE.json"
    gui_acceptance = json.loads(gui_acceptance_path.read_text(encoding="utf-8"))
    version_audit_path = args.validation / "VERSION_BOUNDARY_AUDIT.json"
    version_audit = json.loads(version_audit_path.read_text(encoding="utf-8"))
    if validation.get("status") != "success":
        raise ValueError("v0.4.1 validation is not successful")
    if standalone.get("status") != "success" or not standalone.get("clean_environment"):
        raise ValueError("Standalone clean-environment workflow is not successful")
    if wheel_smoke.get("status") != "success" or wheel_smoke.get("five_step_pages") != 5:
        raise ValueError("Installed-wheel GUI smoke is not successful")
    if gui_acceptance.get("status") != "success":
        raise ValueError("Real GUI user acceptance is not successful")
    if version_audit.get("status") != "success" or not all(
        bool(value) for value in version_audit.get("checks", {}).values()
    ):
        raise ValueError("Frozen-version boundary audit is not successful")
    if sha256(args.phase2_evidence) != PHASE2_EVIDENCE_SHA256:
        raise ValueError("Frozen Phase 2 evidence changed")

    wheel = args.release / "osm_scientific_converter-0.4.1-py3-none-any.whl"
    sdist = args.release / "osm_scientific_converter-0.4.1.tar.gz"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = archive.read(next(name for name in names if name.endswith(".dist-info/METADATA"))).decode("utf-8")
        entry_points = archive.read(next(name for name in names if name.endswith(".dist-info/entry_points.txt"))).decode("utf-8")
        wheel_crc = archive.testzip() is None
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = archive.getnames()
    wheel_validation = {
        "status": "success",
        "wheel_crc": wheel_crc,
        "metadata_version": "Version: 0.4.1" in metadata,
        "pyside_pin": "Requires-Dist: PySide6==6.8.3" in metadata,
        "gui_entry_point": "osm-sci-gui" in entry_points,
        "profiles": sorted(name for name in names if "/resources/profiles/" in name),
        "gui_modules": sorted(name for name in names if "/gui/" in name and name.endswith(".py")),
        "installed_tests": validation["tests"],
        "wheel": {"file": wheel.name, "sha256": sha256(wheel)},
        "sdist": {"file": sdist.name, "sha256": sha256(sdist), "members": len(sdist_names)},
    }
    if not all(wheel_validation[key] for key in ("wheel_crc", "metadata_version", "pyside_pin", "gui_entry_point")):
        raise ValueError("Wheel metadata validation failed")
    if len(wheel_validation["profiles"]) != 3:
        raise ValueError("Wheel does not contain exactly three built-in profiles")
    wheel_validation_path = args.validation / "WHEEL_VALIDATION.json"
    wheel_validation_path.write_text(json.dumps(wheel_validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    source_zip = args.release / "OSM_Scientific_Converter_Phase3_v0.4.1_source_clean.zip"
    source_prefix = "OSM_Scientific_Converter_Phase3_v0.4.1"
    source_count = 0
    with zipfile.ZipFile(source_zip, "w") as archive:
        for path in clean_source_files(args.working):
            write_member(archive, f"{source_prefix}/{path.relative_to(args.working).as_posix()}", path.read_bytes())
            source_count += 1
    with zipfile.ZipFile(source_zip) as archive:
        if archive.testzip():
            raise ValueError("Source ZIP CRC failure")
        forbidden = [name for name in archive.namelist() if "__pycache__" in name or name.endswith((".pyc", ".pyo")) or "v040" in Path(name).name.lower()]
    if forbidden:
        raise ValueError(f"Clean source ZIP contains forbidden files: {forbidden}")
    source_record = {"file": source_zip.name, "sha256": sha256(source_zip), "members": source_count}

    windows_dir = args.windows_dir
    copy_windows_user_materials(args.working, windows_dir)
    required_runtime = [
        windows_dir / "OSMScientificConverter_v0.4.1.exe",
        windows_dir / "_internal" / "ogr2ogr.exe",
        windows_dir / "_internal" / "ogrinfo.exe",
        windows_dir / "_internal" / "gdal_data",
        windows_dir / "_internal" / "proj_data" / "proj.db",
        windows_dir / "_internal" / "PySide6",
        *(windows_dir / name for name in USER_FILES),
        windows_dir / "examples" / "sample_infrastructure.osm",
        windows_dir / "examples" / "expected_output_summary.json",
    ]
    missing = [str(path) for path in required_runtime if not path.exists()]
    if missing:
        raise ValueError(f"Standalone package is missing runtime or user materials: {missing}")
    windows_zip = args.release / "OSMScientificConverter_v0.4.1_Windows_x64.zip"
    windows_record = zip_directory(windows_dir, windows_zip, windows_dir.name)
    windows_record["smoke"] = {
        "status": standalone["status"],
        "workflow": standalone["workflow"],
        "gdal": standalone["environment"]["gdal"]["version"],
        "clean_environment": True,
    }

    frozen_reference = {
        "phase1": {"version": "0.2.3", "modified": False},
        "phase2": {"version": "0.3.1", "evidence_file": args.phase2_evidence.name, "evidence_sha256": PHASE2_EVIDENCE_SHA256, "modified": False},
        "phase3_predecessor": {"version": "0.4.0", "release_json_sha256": V040_RELEASE_SHA256, "modified": False},
        "phase3": {
            "version": VERSION,
            "derived_from": "0.4.0",
            "classification_expressions_unchanged": version_audit["checks"]["all_profile_classification_semantics_unchanged"],
            "profile_hashes_changed_for_expected_field_metadata": version_audit["checks"]["all_v041_profile_hashes_changed"],
            "classifier_source_unchanged": version_audit["checks"]["classifier_source_unchanged"],
            "rule_engine_source_unchanged": version_audit["checks"]["rule_engine_source_unchanged"],
            "scanner_source_unchanged": version_audit["checks"]["scanner_source_unchanged"],
            "classification_schema_unchanged": version_audit["checks"]["classifier_source_unchanged"],
        },
    }
    release_validation = {
        "schema_version": "1.0",
        "status": "success",
        "software_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tests": validation["tests"],
        "real_validation": validation.get("real_validation"),
        "gui_user_acceptance": gui_acceptance,
        "standalone_windows": windows_record,
        "wheel": wheel_validation,
        "frozen_versions": frozen_reference,
    }
    release_validation_path = args.validation / "PHASE3_V041_RELEASE_VALIDATION.json"
    release_validation_path.write_text(json.dumps(release_validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    release = {
        "schema_version": "1.0",
        "software": {"name": "OSM Scientific Converter", "version": VERSION},
        "status": "local_release_candidate_validated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "frozen_versions": frozen_reference,
        "artifacts": {
            "wheel": wheel_validation["wheel"],
            "sdist": wheel_validation["sdist"],
            "source": source_record,
            "windows": windows_record,
            "evidence": {"file": "Phase3_v0.4.1_validation_evidence_final.zip", "sha256_recorded_in": "SHA256SUMS.txt"},
        },
        "public_release_metadata": {
            "complete": False,
            "missing_verified_values": [
                "actual authors and affiliations",
                "ORCID if applicable",
                "corresponding author and contact",
                "conflict-of-interest statement",
                "GitHub repository",
                "GitHub release URL",
                "Zenodo DOI",
                "software and data availability URLs",
            ],
            "note": "No identity, repository URL, or DOI was inferred or fabricated during local validation.",
        },
    }
    release_json = args.release / "RELEASE_V041.json"
    release_json.write_text(json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    evidence_files = sorted(path for path in args.validation.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt", ".csv", ".png"})
    materialized: list[tuple[str, bytes]] = [(path.relative_to(args.validation).as_posix(), path.read_bytes()) for path in evidence_files]
    materialized.extend([
        ("RELEASE_V041.json", release_json.read_bytes()),
        ("FROZEN_VERSION_REFERENCE.json", (json.dumps(frozen_reference, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")),
        ("OSM_ATTRIBUTION_AND_ODBL.md", (args.working / "OSM_ATTRIBUTION_AND_ODBL.md").read_bytes()),
    ])
    evidence_internal_sums = "".join(f"{sha256_bytes(data)}  {name}\n" for name, data in sorted(materialized))
    materialized.append(("SHA256SUMS.txt", evidence_internal_sums.encode("utf-8")))
    evidence_zip = args.release / "Phase3_v0.4.1_validation_evidence_final.zip"
    with zipfile.ZipFile(evidence_zip, "w") as archive:
        for name, data in sorted(materialized):
            write_member(archive, name, data)
    with zipfile.ZipFile(evidence_zip) as archive:
        if archive.testzip():
            raise ValueError("Evidence ZIP CRC failure")

    artifacts = [wheel, sdist, source_zip, windows_zip, evidence_zip, release_json]
    sums = args.release / "SHA256SUMS.txt"
    sums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(artifacts)), encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": "success",
        "artifacts": len(artifacts) + 1,
        "source_sha256": source_record["sha256"],
        "windows_sha256": windows_record["sha256"],
        "evidence_sha256": sha256(evidence_zip),
        "release_json_sha256": sha256(release_json),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
