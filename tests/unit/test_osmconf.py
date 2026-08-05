from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _config_text() -> str:
    return (ROOT / "config" / "osmconf.ini").read_text(encoding="utf-8")


def test_all_tags_early_filtering_is_disabled():
    text = _config_text()
    assert "report_all_tags=yes" in text
    assert "tags_format=json" in text
    for section in ("points", "lines", "multipolygons", "multilinestrings", "other_relations"):
        assert f"[{section}]" in text
    assert sum(line.strip() == "all_tags=yes" for line in text.splitlines()) == 5


def test_linear_infrastructure_is_not_blanket_promoted_to_polygon():
    general = _config_text().split("[points]", 1)[0]
    polygon_line = next(
        line for line in general.splitlines()
        if line.startswith("closed_ways_are_polygons=")
    )
    values = polygon_line.split("=", 1)[1].split(",")
    assert "power" not in values
    assert "man_made" not in values
    assert "waterway" not in values
    assert "power=substation" in values
    assert "man_made=storage_tank" in values
