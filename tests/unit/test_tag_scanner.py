from osm_scientific_converter.core.tag_scanner import parse_tags


def test_json_unicode_multivalue_and_empty_values():
    tags, anomaly = parse_tags('{"name":"中文","voltage":"110000;220000","empty":""}')
    assert tags == {"name": "中文", "voltage": "110000;220000", "empty": ""}
    assert anomaly is None


def test_legacy_hstore_is_diagnosed_and_parsed():
    tags, anomaly = parse_tags('"power"=>"line","name"=>"A \\"quoted\\" name"')
    assert tags["power"] == "line"
    assert anomaly == "legacy_hstore"


def test_malformed_json_is_countable():
    tags, anomaly = parse_tags("{bad json")
    assert tags == {}
    assert anomaly == "malformed_all_tags"


def test_null_and_non_object_json_are_not_silent():
    assert parse_tags(None)[1] == "empty_all_tags"
    assert parse_tags("[]")[1] == "non_object_all_tags"

