from osm_scientific_converter.core.raw_importer import _aggregate_warnings


def test_repeated_gdal_warnings_are_aggregated():
    text = "\n".join([
        "Warning 1: Non closed ring detected",
        "Warning 1: Non closed ring detected",
        "ordinary diagnostic",
    ])
    assert _aggregate_warnings(text) == [
        {"message": "Warning 1: Non closed ring detected", "count": 2},
    ]
