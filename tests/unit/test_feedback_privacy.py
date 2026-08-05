import json
import zipfile

from osm_scientific_converter.core.feedback import build_feedback_bundle


def test_feedback_excludes_full_inventories_and_databases(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "project_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "raw_inventory.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tag_inventory.csv").write_text("sensitive", encoding="utf-8")
    (tmp_path / "tag_inventory.json").write_text("sensitive", encoding="utf-8")
    (tmp_path / "lifecycle_inventory.csv").write_text("sensitive", encoding="utf-8")
    (tmp_path / "data" / "inventory.sqlite").write_bytes(b"sqlite")
    bundle = build_feedback_bundle(tmp_path)
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "project_manifest.json" in names
        assert "raw_inventory.json" in names
        assert "tag_inventory.csv" not in names
        assert "tag_inventory.json" not in names
        assert "lifecycle_inventory.csv" not in names
        assert not any(name.endswith((".sqlite", ".gpkg", ".osm", ".pbf")) for name in names)
