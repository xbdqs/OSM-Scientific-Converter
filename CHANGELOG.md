# Changelog

## 0.4.1 — 2026-08-04

- Made GUI field selection control the exported profile-attribute subset while enforcing ten minimum provenance fields.
- Replaced first-object quality sampling with deterministic category × geometry stratification seeded by the input hash.
- Added category-applicable required, recommended, and optional field expectations with explicit denominators.
- Renamed the leaf editor to the simple rule builder and added an editable advanced JSON profile dialog backed by the core validator and parsed summary.
- Preserved selected key/value state across pagination, search, reload, and project save/load, with per-key/all clear controls.
- Added bilingual user documentation, a quick start, notices, OSM attribution/ODbL guidance, and a synthetic example to the Windows distribution contract.
- Defined one formal artifact set: wheel, sdist, clean source ZIP, Windows ZIP, validation evidence ZIP, `RELEASE_V041.json`, and `SHA256SUMS.txt`.
- Preserved the v0.4.0 GUI architecture and the frozen Phase 1 v0.2.3 / Phase 2 v0.3.1 directories.

## 0.4.0 — 2026-08-04

- Added a five-step PySide6 desktop workflow for input, inventory overview, selection, preview/quality checks, and export.
- Added drag-and-drop input, system/environment inspection, worker-thread core operations, cancellation, progress logs, and diagnostic feedback reporting.
- Added read-only paginated inventory queries, built-in profile/category selection, dynamic key/value filtering, and a validated custom-rule builder.
- Added bounded QGraphicsScene map preview with pan/zoom, category visibility, object selection, and full tag inspection.
- Added deterministic pre-export quality checks and atomic `project.osmproject.json` persistence; automatic repair remains disabled.
- Kept Phase 2 v0.3.1 rules, profile hashes, classification SQLite schema, and exporter semantics unchanged.

## 0.3.1 — 2026-08-03

- Replaced absolute project/output paths in Phase 2 reports and feedback payloads with project-relative or redacted paths.
- Replaced universal `lossless_claim` wording with explicit truncation, full-tags, and GDAL/OGR geometry-conversion audit fields.
- Tightened pipeline storage, pumping, and compressor rules; context-free objects are candidate categories excluded from default export.
- Added ten positive and ten negative pipeline context regression cases.
- Explicitly closed SQLite connections and passed strict warning-as-error tests on Python 3.12.13 and 3.13.14.
- Declared the formally tested Python range as `>=3.12,<3.14`.

## 0.3.0 — 2026-08-03

- Added versioned built-in power, pipeline, and aeroway profiles plus custom JSON profile/rule loading.
- Added nested string, numeric, unit-aware, lifecycle, geometry, layer, and OSM-type rule evaluation.
- Added streamed classification SQLite output with multi-rule matches and object/rule/profile traceability.
- Added GPKG, GeoJSON, and Shapefile exports with field mapping and explicit format-loss audits.
- Added the three-stage `extract` command while retaining the raw master and intermediate project.
- Added privacy-minimized Phase 2 feedback bundles that exclude geometry, raw tags, object IDs, and databases.
- Added high-cardinality bounded-memory, profile, classification, export, and privacy regression coverage; 47 strict tests pass.
- Validated Berlin/power, South Korea/aeroway, and New York/pipeline real PBF workflows, including 16 fixed manual OSM ID references.
- Tightened pipeline substance and usage rules to require explicit pipeline context after manual false-positive review.
- Kept the validated Phase 1 v0.2.3 release frozen and separated from the Phase 2 v0.3.0 working/release artifacts.

## 0.2.3 — 2026-08-03

- Completed Windows validation with stable GDAL 3.13.2 on Berlin, South Korea, New York, and Quebec PBF extracts.
- Confirmed deterministic tag and lifecycle CSV hashes across the development and stable GDAL validation runs.
- Reduced the New York workload peak from about 12.65 GiB in v0.2.1 to about 549 MiB.
- Stored project-internal paths as portable relative paths in `raw_inventory.json`.
- Aggregated repeated successful-import GDAL warnings in both the manifest and scan log.
- Hardened resource monitoring against child-process exit races.
- Ensured the reported overall RSS peak always includes the independently sampled import peak.
- Expanded the strict test suite to 21 passing tests.

## 0.2.2 — 2026-08-03

- Replaced unbounded in-memory tag aggregation with bounded chunks and a SQLite aggregate store.
- Streamed tag JSON/CSV and lifecycle CSV directly from SQLite cursors.
- Added retained `data/inventory.sqlite` as the canonical queryable inventory for later GUI development.
- Added whole-task RSS and working-disk monitoring for the Python process and child processes.
- Aggregated repeated GDAL warnings by message and count.
- Minimized feedback bundles by excluding full inventories and all geometry/database files.
- Added a reproducibility warning for GDAL development or dirty builds.
- Added inventory-store, streaming-report, and feedback-privacy regression tests.

## 0.2.1 — 2026-08-02

- Enabled `report_all_tags=yes` to prevent GDAL early tag filtering.
- Required GDAL 3.10+ for consistent `[general]` configuration handling.
- Replaced broad closed-way polygon rules with explicit area-capable values.
- Clarified reconstructed object counts versus raw OSM base-object totals.
- Made post-commit backup cleanup non-fatal.
- Added configuration regression tests.

## 0.2.0 — 2026-08-02

- Added `.osm`/`.pbf` content validation and streaming SHA-256.
- Added GDAL/OGR/SQLite environment and driver diagnostics.
- Added staged five-layer OSM-to-GeoPackage reconstruction with JSON `all_tags`.
- Added deterministic tag, geometry, object-type, and lifecycle inventories.
- Added atomic project commit, non-destructive overwrite, structured logs, and failure diagnostics.
- Added privacy-safe feedback bundles, synthetic integration data, tests, and Windows wrappers.
