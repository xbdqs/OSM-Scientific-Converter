from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt

from osm_scientific_converter.core.inventory_store import InventoryStore
from osm_scientific_converter.gui.inventory import InventoryRepository
from osm_scientific_converter.gui.main_window import SelectionPage


def make_inventory(project: Path, keys: int = 1200, values: int = 230) -> InventoryRepository:
    database = project / "data" / "inventory.sqlite"
    with InventoryStore(database, create=True) as store:
        store.upsert_tags((f"key_{index:04d}", f"value_{index % values:03d}", "points", "point", index + 1, "[]") for index in range(keys))
        store.upsert_tags(("high_cardinality", f"value_{index:03d}", "lines", "line", 1000 - index, "[]") for index in range(values))
        store.upsert_key_cross((f"key_{index:04d}", "points", "point", index + 1) for index in range(keys))
        store.upsert_lifecycle([("abandoned", "abandoned=yes", "points", "point", 4, "[]")])
    return InventoryRepository(project)


def test_large_key_inventory_is_bounded_and_sorted(tmp_path):
    repository = make_inventory(tmp_path)
    rows = repository.keys(limit=500)
    assert len(rows) == 500
    assert rows[0]["count"] >= rows[-1]["count"]
    searched = repository.keys(search="key_1199", limit=500)
    assert [row["key"] for row in searched] == ["key_1199"]


def test_value_search_and_pagination(tmp_path):
    repository = make_inventory(tmp_path)
    first = repository.values("high_cardinality", page=0, page_size=100)
    third = repository.values("high_cardinality", page=2, page_size=100)
    searched = repository.values("high_cardinality", search="value_229", page=0, page_size=100)
    assert first["total"] == 230 and len(first["rows"]) == 100
    assert len(third["rows"]) == 30
    assert searched["rows"][0]["value"] == "value_229"


def test_selection_page_delays_values_until_key_click(qtbot, tmp_path):
    repository = make_inventory(tmp_path)
    page = SelectionPage()
    qtbot.addWidget(page)
    page.set_repository(repository)
    qtbot.waitUntil(lambda: page.key_tree.topLevelItemCount() > 0)
    assert page.value_table.rowCount() == 0
    item = page.key_tree.topLevelItem(0)
    page._key_clicked(item)
    assert page.value_table.rowCount() <= 100


def test_dynamic_checked_values_generate_rule(qtbot, tmp_path):
    repository = make_inventory(tmp_path)
    page = SelectionPage(); qtbot.addWidget(page); page.set_repository(repository)
    page.current_key = "high_cardinality"; page.load_values(0)
    page.value_table.item(0, 0).setCheckState(Qt.Checked)
    page.build_dynamic_profile()
    assert '"op": "in"' in page.rule_preview.toPlainText()


def test_value_selections_persist_across_pages_search_and_reload(qtbot, tmp_path):
    repository = make_inventory(tmp_path)
    page = SelectionPage(); qtbot.addWidget(page); page.set_repository(repository)
    page.current_key = "high_cardinality"; page.load_values(0)
    first_value = page.value_table.item(0, 1).text()
    page.value_table.item(0, 0).setCheckState(Qt.Checked)
    page.load_values(1)
    second_value = page.value_table.item(0, 1).text()
    page.value_table.item(0, 0).setCheckState(Qt.Checked)
    page.load_values(0)
    assert page.value_table.item(0, 0).checkState() == Qt.Checked
    page.value_search.setText(first_value)
    page.load_values(0)
    assert page.value_table.item(0, 0).checkState() == Qt.Checked
    assert page.selected_tag_values()["high_cardinality"] == sorted([first_value, second_value])
    page.clear_current_selection()
    assert "high_cardinality" not in page.selected_tag_values()
