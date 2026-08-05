import json
from pathlib import Path

from osm_scientific_converter.core.inventory_store import InventoryStore


def test_disk_store_merges_counts_and_samples(tmp_path):
    path = tmp_path / "inventory.sqlite"
    with InventoryStore(path, create=True) as store:
        store.upsert_tags([
            ("power", "line", "lines", "line", 2, '["way/1","way/2"]'),
            ("power", "line", "lines", "line", 3, '["way/2","way/3","way/4"]'),
        ])
        store.upsert_lifecycle([
            ("construction", "construction:power=line", "lines", "line", 1, '["way/9"]'),
        ])
        store.upsert_key_cross([
            ("power", "lines", "line", 2),
            ("power", "lines", "line", 3),
        ])
        store.commit()
        row = next(store.iter_tags())
        assert row["count"] == 5
        assert row["sample_osm_ids"] == ["way/1", "way/2", "way/3", "way/4"]
        assert store.counts() == {
            "tag_inventory_rows": 1,
            "lifecycle_inventory_rows": 1,
            "unique_keys": 1,
            "unique_key_values": 1,
        }
        assert store.key_layer_geometry()[0]["count"] == 5
