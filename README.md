# OSM Scientific Converter v0.4.1

OSM Scientific Converter is an auditable desktop and command-line workflow for scientific preparation of thematic OpenStreetMap (OSM) datasets from a dated local `.osm` or `.osm.pbf` snapshot. It inventories the tag vocabulary actually present in the supplied snapshot, reconstructs the five logical layers exposed by the GDAL OSM driver, applies versioned JSON profiles, preserves object/rule provenance, performs deterministic process checks, and exports GeoPackage, GeoJSON, or Shapefile with explicit export-audit evidence.

The validated software release remains **v0.4.1**. This peer-review update changes documentation and publication figures only; it does not change the released scanner, classifier, rule evaluator, built-in profiles, exporter, database schema, tests, or binaries.

## Scientific scope

The software addresses **reproducible thematic data preparation**, not OSM filtering as a novel operation and not external ground-truth validation. For a fixed local snapshot, it preserves three linked forms of provenance:

- **Data provenance:** input SHA-256, OSM object/source representation, and environment.
- **Semantic provenance:** observed tag inventory, resolved profile/rules, lifecycle handling, candidate/confirmed distinctions, and profile SHA-256.
- **Computational/export provenance:** software release, project configuration, deterministic checks, output schema, mappings, and observed format losses.

Results describe the supplied snapshot and selected rules. They do not guarantee physical infrastructure completeness, positional accuracy, or universal thematic correctness of OSM.

## Five-step desktop workflow

1. Select the input and project directory; record input SHA-256 and the GDAL/memory/disk environment.
2. Browse the disk-backed layer, tag, lifecycle, and warning inventory with lazy key/value queries.
3. Apply a built-in `power`, `pipeline`, or `aeroway` profile, select from observed keys/values, or validate a custom JSON profile.
4. Review a bounded map preview and deterministic category × geometry process checks.
5. Select categories/attributes and export to GeoPackage, GeoJSON, or Shapefile with mandatory provenance and format-loss reporting.

Run `osm-sci --help` for the CLI or `osm-sci-gui` for the desktop application. The Windows release contains the packaged English GUI used for the manuscript workflow screenshots.

## Related tools and positioning

OSM filtering and conversion are mature capabilities. GDAL provides the low-level OSM reconstruction engine used here; osm2pgsql is well suited to persistent PostgreSQL/PostGIS and large/planet-scale database workflows; Osmosis and osmconvert provide command-line file processing; QuickOSM supports QGIS/Overpass workflows; OSMnx standardizes programmatic OSM acquisition/analysis; OSM2CDR provides online conversion; and ohsome supports temporal OSM queries and statistics.

The narrower contribution of OSM Scientific Converter is to combine **snapshot-specific vocabulary discovery, explicit/versioned semantic rules, object-level provenance, deterministic extraction-process checks, GUI/CLI parity, and format-loss evidence** in one local project. See `docs/SCIENTIFIC_SCOPE_AND_RELATED_TOOLS.md`.

## Profile authoring

Built-in profiles are examples of explicit semantic definitions, not universal ontologies. A defensible profile is developed by scanning the target snapshot, inspecting observed key/value and geometry/lifecycle distributions, consulting OSM/domain knowledge, encoding inclusive/exclusive/candidate logic, reviewing category totals and deterministic samples, and freezing the resolved JSON with a SHA-256. Taginfo and ohsome can provide external context but do not replace the local inventory. See `docs/PROFILE_AUTHORING.md`.

## Empirical scalability boundary

Validated v0.4.1 workflows cover Berlin (94.2 MiB), South Korea (271.3 MiB), New York (471.4 MiB), and Quebec (1.08 GiB), with up to 12.38 million reconstructed features and complete-workflow peak RSS of 481.1-633.1 MiB on the tested workstation. These measurements support the stated regional and tested national workflows; they are **not** a planet-scale benchmark. See `docs/SCALABILITY_AND_LIMITS.md`.

## Output formats

- **GeoPackage:** implemented and default; standards-based evidence-bearing analytical output.
- **GeoJSON:** implemented; transparent text interchange.
- **Shapefile:** implemented for legacy interoperability; field mappings and observed losses are reported.
- **GeoParquet:** discussed as a future analytical extension and **not implemented in v0.4.1**.

See `docs/FORMAT_SUPPORT.md`.

## Reproducibility and project evidence

`project.osmproject.json` records input/profile hashes, resolved rules, selections, quality/export settings, and run results. Project evidence includes the disk-backed inventory, classification summaries/database, export audits, field mappings, loss reports, and minimized diagnostics. Reproducibility comparisons require the same input bytes, v0.4.1 release, profile SHA-256, and selection/configuration.

The code is MIT licensed. OSM data are subject to the applicable OpenStreetMap/Open Database License terms; see `OSM_ATTRIBUTION_AND_ODBL.md`. Third-party runtime and publication-figure notices are in `THIRD_PARTY_NOTICES.md`.

## Publication figures and evidence

The revised SoftwareX manuscript uses **six figures**, all mirrored under `paper/figures/` with source data and reproducible Python code:

1. software architecture and evidence flow;
2. the actual five-step English GUI captured from the packaged v0.4.1 Windows application during the Berlin power workflow;
3. representative locations of the four validation extracts (Natural Earth public-domain basemap; markers are not exact Geofabrik boundaries);
4. major thematic categories for Berlin power, South Korea aeroway, and New York pipeline;
5. observed Berlin export audit plus repeated-run reproducibility checks; and
6. measured workflow time and peak resident memory.

Public validation summaries are stored in `validation/public/`. Regional PBF inputs and private project databases are intentionally excluded.
