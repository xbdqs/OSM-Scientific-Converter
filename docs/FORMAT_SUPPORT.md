# Output formats and design rationale

| Format | v0.4.1 status | Primary role | Relevant constraint / audit interpretation |
|---|---|---|---|
| GeoPackage | Implemented; default | Standards-based evidence-bearing analytical output | Portable SQLite container with multi-layer support; tested exports retained complete `tags_json` and showed no detected field-name/value truncation. |
| GeoJSON | Implemented | Transparent text interchange | Human-/web-readable but verbose for large datasets; output semantics are audited rather than assumed identical to other formats. |
| Shapefile | Implemented | Legacy interoperability | DBF field-name/type/width constraints; the software records mappings and observed truncation instead of treating legacy limitations as a software discovery. |
| GeoParquet | Not implemented | Potential future columnar analytical output | Would require a separately validated exporter covering geometry metadata, schema/provenance, partitioning, interoperability, and round-trip/loss behavior. |

GeoPackage is not presented as a competitive discovery over Shapefile. Its default status is a standards-informed design choice for evidence-bearing research output. The exporter reports transformations and losses observed for the actual output rather than describing any format as universally lossless.

Specifications cited in the manuscript are OGC GeoPackage 1.4.0, RFC 7946 GeoJSON, the Esri Shapefile Technical Description plus the GDAL Shapefile/DBF driver documentation, and GeoParquet 1.1.0 for the future-scope discussion.
