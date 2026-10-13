# v0.4.1 machine-evidence results

> Generated from the final local evidence files. Reference-set metrics remain provisional until independent human/domain review. QuickOSM and a same-snapshot prepared Shapefile were not available and are not simulated.

## Artifact and test identity

- Software version: `0.4.1`
- Tested wheel SHA-256: `b882fb9988a7e9adec3c561f7e28563d16f54a11b28dfe806eacfc4597f63ec3`
- Strict test runs: 4; each run passed 90 tests with warnings treated as errors.

## Four-region performance

| Case | Input MiB | Scanned objects | Matched objects | Import s | Inventory s | Classification s | Preview s | Quality s | Export s | Peak RSS MiB | Output MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| berlin_power | 94.2 | 2525682 | 6726 | 44.929 | 81.877 | 107.040 | 0.465 | 0.094 | 9.873 | 481.1 | 3.7 |
| new_york_pipeline | 471.4 | 11434477 | 3078 | 189.195 | 716.245 | 2175.550 | 0.406 | 0.063 | 2.079 | 633.1 | 1.1 |
| quebec_power | 1104.5 | 12382811 | 475166 | 261.806 | 260.935 | 514.643 | 0.675 | 5.089 | 747.195 | 616.4 | 133.9 |
| south_korea_aeroway | 271.3 | 4587351 | 9304 | 92.222 | 210.284 | 193.463 | 0.278 | 0.090 | 13.860 | 604.5 | 4.0 |

All four cases require equal repeated classification counts and OSM ID sets, equal repeated export feature/layer counts, equal input/profile hashes, and `ok` SQLite/GPKG integrity. Byte-identical database files are not required.

## Provisional tag-semantic reference sets

| Topic | Positive | Negative | Geometry coverage | Regions | Lifecycle cases | Precision | Recall | F1 | Coverage check |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| aeroway | 50 | 30 | line, point, polygon, relation | 4 | 16 | 0.905660 | 0.960000 | 0.932039 | success |
| pipeline | 50 | 30 | line, point, polygon, relation | 4 | 10 | 0.701493 | 0.940000 | 0.803419 | success |
| power | 50 | 30 | line, point, polygon, relation | 4 | 16 | 0.978723 | 0.920000 | 0.948454 | success |

Reference review status: `provisional_agent_adjudication_complete_independent_human_review_pending`. These metrics measure agreement with explicit OSM tag-semantic adjudication, not physical asset ground truth, and are not publication-ready accuracy claims before independent review.

## Partial tool comparison

- GDAL default target OSM ID recall: 6726/6726 (1.000000).
- Exact tag key/value retention: 41179/42376 (0.971753).
- Target relations recalled: 3/3.
- Lifecycle objects with still-detectable lifecycle tags: 272/272.
- QuickOSM: `not_executed` — QGIS/QuickOSM is not installed locally.
- Prepared Shapefile: `not_executed` — No product, version, same-snapshot date, or matching extent was supplied.

## Packaged GUI acceptance

- `berlin_power`: success; 8 checks; 4 screenshots; wall time 57.401 s.
- `new_york_pipeline`: success; 8 checks; 4 screenshots; wall time 2187.616 s.
- `south_korea_aeroway`: success; 8 checks; 4 screenshots; wall time 239.737 s.

Acceptance was programmatic through real packaged GUI widgets and captured windows; it is not described as manual mouse testing.

## Submission decision

The local v0.4.1 software candidate may be frozen and hashed when all machine checks pass. Manuscript submission remains blocked by independent reference review, the complete QuickOSM/prepared-Shapefile comparison, verified authorship/affiliation/contact and competing-interest metadata, a public repository/release, Zenodo DOI, and software/data availability URLs.
