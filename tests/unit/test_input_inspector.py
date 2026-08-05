import pytest

from osm_scientific_converter.core.input_inspector import InputValidationError, inspect_input


def test_inspects_osm_and_bounds(tmp_path):
    path = tmp_path / "输入.osm"
    path.write_text('<?xml version="1.0"?><osm version="0.6"><bounds minlat="1" minlon="2" maxlat="3" maxlon="4"/></osm>', encoding="utf-8")
    result = inspect_input(path)
    assert result.format == "osm"
    assert result.bounds == [2.0, 1.0, 4.0, 3.0]


def test_rejects_extension_content_mismatch(tmp_path):
    path = tmp_path / "bad.osm"
    path.write_text("not osm", encoding="utf-8")
    with pytest.raises(InputValidationError):
        inspect_input(path)

