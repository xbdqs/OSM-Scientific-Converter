from osm_scientific_converter.core.models import TagInventoryRecord


def test_sample_ids_are_unique_and_bounded():
    record = TagInventoryRecord("k", "v", "lines", "line")
    for value in ["1", "1", "2", "3", "4", "5", "6"]:
        record.observe(value)
    assert record.count == 7
    assert record.sample_osm_ids == ["1", "2", "3", "4", "5"]
    assert record.to_dict()["key"] == "k"

