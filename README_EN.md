# OSM Scientific Converter v0.4.2

OSM Scientific Converter provides reproducible, rule-driven thematic extraction from local OpenStreetMap `.osm` / `.osm.pbf` snapshots. Source code is MIT-licensed; OSM-derived data retains ODbL/attribution obligations.

## Two distinct workflows

**Full auditable project:** five-stage GUI (input and scan, tag-vocabulary overview, versioned thematic rules, bounded preview and stratified quality sampling, export) and `osm-sci scan`, `classify`, `export`. Built-in themes include power, pipeline and aeroway. Full project mode supports GPKG, GeoJSON and Shapefile with format-specific audit records.

**Quick roads (no scan):** targeted `highway` selection from the **exact GDAL `lines` source layer** using a reviewed 13-value / four-class rule profile; available from the Step 1 GUI dialog and `osm-sci quick-extract`. It creates a GeoPackage and SHA-256-bound audit sidecar without a full tag-vocabulary inventory or complete pre-export quality audit. It still parses/reconstructs data using GDAL, so it is not a guarantee of early PBF byte filtering. The GUI map shows a **bounded, first-400-objects visual sample**, not a spatially representative or exhaustive validation.

```shell
# With GDAL 3.13.x CLI and Python bindings accessible in the active conda environment:
python -m pip install -e '.[test]'
python -m pytest -q
osm-sci --version
osm-sci-gui
osm-sci quick-extract examples/round2_roads_small.osm --rules src/osm_scientific_converter/resources/profiles/reviewer_roads_lines_v1.json --output quick_example.gpkg
```

For scientific interpretation: the four highway categories are **specific whitelist classes**, not a complete road-network inventory. Input snapshot and rule-profile hashes determine the result. Quick outputs do not carry the full inventory or full QA guarantees of the original workflow. Partial direct-GDAL comparisons must not be described as like-for-like full-workflow benchmarking.

## Installation and distribution

See `RELEASE_NOTES_v0.4.2.md`, `RELEASE_VALIDATION_CHECKLIST_CN.md`, `QUICK_START_CN.md`, and `tools/build_windows_v042.ps1`. Building the **Windows standalone EXE requires Windows/Conda/GDAL/PyInstaller**. A source/wheel artifact built on Linux is not a substitute for a validated Windows EXE. Do not publish any Windows ZIP unless its packaged GUI + headless quick-extract smoke tests pass.

## Reproducibility and publication artifacts

- `tests/` contains unit, GUI and GDAL integration tests.
- `examples/` contains synthetic datasets and reviewed rules.
- `validation/round2_v042/` keeps version-labelled, data-minimized performance evidence.
- `validation/historical_v041/` and `tools/legacy_v041/` are historical v0.4.1-only records; they do not certify the new release.
- `paper/figures/` contains earlier figure scripts and supporting tabulations, not regenerated v0.4.2 figures.

**Licensing:** Source code MIT (`LICENSE`). OSM inputs/extracts and produced maps may require © OpenStreetMap contributors attribution/ODbL compliance. Third-party components maintain their own licenses (`THIRD_PARTY_NOTICES.md`).
