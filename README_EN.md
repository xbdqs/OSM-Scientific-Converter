# OSM Scientific Converter v0.4.1

OSM Scientific Converter is an auditable OpenStreetMap scanning, rule-classification, and thematic-export application for scientific data preparation. It discovers tags from the supplied snapshot, reconstructs five OSM-aware layers, applies versioned and explainable JSON profiles, and exports GPKG, GeoJSON, or Shapefile.

v0.4.1 is a hardening release derived from frozen v0.4.0. The classifier, rule evaluator, scanner, classification expressions, and classification database schema are unchanged. The three v0.4.1 profile files intentionally have new SHA-256 values because they add category-applicable expected-field metadata; do not mix their hashes with v0.4.0 evidence.

## Scientific boundaries

- Inputs are local `.osm` or `.osm.pbf` snapshots; the software does not download or refresh OSM data.
- Results describe the supplied snapshot and rules, not guaranteed real-world infrastructure completeness.
- Native output is EPSG:4326; no silent reprojection is performed.
- Automatic geometry repair is disabled and not implemented.
- Map preview is bounded to 2,000 objects. Quality geometry checks use a deterministic stratified sample rather than claiming a full census.
- Shapefile has measurable field-name, text-width, and Unicode compatibility risks; inspect the generated loss report.

## Five-step desktop workflow

1. Select an input and a new project directory; verify SHA-256 and the GDAL, memory, and disk environment.
2. Browse the disk-backed inventory, Top-N tags, lifecycle states, and scan warnings.
3. Select a built-in power, pipeline, or aeroway profile; create a simple rule from paginated key/value selections; or edit and validate an advanced nested JSON profile.
4. Review the bounded map and the deterministic category × geometry quality sample.
5. Select categories, a real profile-attribute subset, and an output format. Ten minimum provenance fields are always retained.

Run `osm-sci --help` for the CLI or `osm-sci-gui` for the desktop application. The Windows ZIP contains a standalone EXE and a synthetic example.

## Reproducibility

`project.osmproject.json` atomically records the input/profile hashes, rules, selections, export and quality settings, and run results. Core evidence includes classification summaries, `classification.sqlite`, export audits, field mappings, Shapefile loss reports, and minimized diagnostic bundles. Reproducibility comparisons must use the same input, v0.4.1 release, profile SHA-256, and selection/configuration.

The code is MIT licensed. OSM data is normally subject to the Open Database License; see `OSM_ATTRIBUTION_AND_ODBL.md`. Third-party runtime notices are in `THIRD_PARTY_NOTICES.md`.
