"""CLI regression: --experimental-deferred-index must reach the actual worker.

No GDAL dependency: validates CLI wiring, including fail-closed confirmation.
The real GeoPackage RTree checks are covered by the GDAL integration tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from osm_scientific_converter.cli import main as cli


@pytest.mark.parametrize("deferred", [False, True], ids=["default", "deferred"])
def test_cli_forwards_deferred_index_flag(monkeypatch, tmp_path, capsys, deferred):
    captured = {}
    resolved = object()
    monkeypatch.setattr(cli, "resolve_profile", lambda **kwargs: resolved)

    def mock_targeted(input_path, output_path, profile, *, base_config, overwrite,
                      experimental_deferred_index):
        captured.update({
            "input_path": input_path,
            "output_path": output_path,
            "profile": profile,
            "base_config": base_config,
            "overwrite": overwrite,
            "deferred": experimental_deferred_index,
        })
        return {
            "status": "success",
            "experimental_deferred_index": experimental_deferred_index,
            "spatial_index": {
                "mode": "deferred_then_created" if experimental_deferred_index
                        else "default_gdal_creation"
            },
        }

    monkeypatch.setattr(cli, "targeted_highway_extract", mock_targeted)
    args = [
        "quick-extract", str(tmp_path / "input.osm"),
        "--rules", str(tmp_path / "rules.json"),
        "--output", str(tmp_path / "roads.gpkg"),
        "--base-config", str(tmp_path / "osmconf.ini"),
    ]
    if deferred:
        args.append("--experimental-deferred-index")
    result = cli.main(args)
    assert result == 0
    assert captured["deferred"] is deferred
    assert captured["profile"] is resolved
    assert captured["input_path"] == tmp_path / "input.osm"
    assert captured["output_path"] == tmp_path / "roads.gpkg"
    assert captured["base_config"] == tmp_path / "osmconf.ini"
    assert captured["overwrite"] is False
    report = json.loads(capsys.readouterr().out)
    assert report["experimental_deferred_index"] is deferred


def test_cli_rejects_silent_default_fallback(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "resolve_profile", lambda **kwargs: object())

    def mock_wrong_report(*args, **kwargs):
        assert kwargs["experimental_deferred_index"] is True
        return {
            "status": "success",
            "experimental_deferred_index": False,
            "spatial_index": {"mode": "default_gdal_creation"},
        }

    monkeypatch.setattr(cli, "targeted_highway_extract", mock_wrong_report)
    code = cli.main([
        "quick-extract", str(tmp_path / "input.osm"),
        "--rules", str(tmp_path / "rules.json"),
        "--output", str(tmp_path / "roads.gpkg"),
        "--base-config", str(tmp_path / "osmconf.ini"),
        "--experimental-deferred-index",
    ])
    assert code != 0
    assert "does not confirm deferred RTree" in capsys.readouterr().err
