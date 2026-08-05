import csv
import json

from osm_scientific_converter.core.inventory_store import InventoryStore
from osm_scientific_converter.core.reports import write_lifecycle_inventory, write_tag_inventory


def test_streamed_reports_match_store_order(tmp_path):
    db = tmp_path / "inventory.sqlite"
    with InventoryStore(db, create=True) as store:
        store.upsert_tags([
            ("z", "2", "lines", "line", 1, '["way/2"]'),
            ("a", "1", "points", "point", 1, '["node/1"]'),
        ])
        store.upsert_lifecycle([
            ("proposed", "proposed:power=line", "lines", "line", 1, '["way/2"]'),
        ])
    write_tag_inventory(tmp_path, db)
    write_lifecycle_inventory(tmp_path, db)
    rows = json.loads((tmp_path / "tag_inventory.json").read_text(encoding="utf-8"))
    assert [row["key"] for row in rows] == ["a", "z"]
    with (tmp_path / "tag_inventory.csv").open(encoding="utf-8-sig", newline="") as stream:
        assert [row["key"] for row in csv.DictReader(stream)] == ["a", "z"]
