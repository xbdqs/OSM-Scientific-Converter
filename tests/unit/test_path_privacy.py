from osm_scientific_converter.core.path_privacy import (
    contains_absolute_path,
    portable_profile_source,
    redact_absolute_paths_in_text,
    sanitize_paths,
)


def test_json_path_sanitizer_removes_drive_username_parent_and_temp_paths():
    payload = {
        "project": r"D:\Private\Users\alice\project",
        "temp": r"C:\Users\alice\AppData\Local\Temp\osm-sci-123",
        "nested": [r"\\server\share\secret\result.gpkg", "/home/alice/private/output.json"],
        "relative": "classification/classification.sqlite",
    }
    sanitized = sanitize_paths(payload)
    assert not contains_absolute_path(sanitized)
    text = str(sanitized)
    assert "alice" not in text
    assert "D:\\Private" not in text
    assert "AppData" not in text
    assert sanitized["relative"] == "classification/classification.sqlite"


def test_text_and_custom_profile_sources_are_redacted():
    text = redact_absolute_paths_in_text(r"opened D:\Private\alice\rules.json")
    assert "D:\\Private" not in text
    assert "alice" not in text
    assert text.endswith("<redacted-path>/rules.json")
    assert portable_profile_source(r"D:\Private\alice\rules.json") == "custom:rules.json"
    assert portable_profile_source("builtin:power") == "builtin:power"
