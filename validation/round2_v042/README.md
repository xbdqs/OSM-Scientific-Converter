# Historical Round 2 real-PBF benchmark (development build)

Records originated from the locally tested **0.4.2.dev1** software build; they were not rerun against the 0.4.2 release package. Preserve original SHA-256 and software-version provenance. The direct-GDAL baseline omits category/provenance enrichment and full inventory. One 856,168,766-byte fixed Sudeste PBF produced 2,067,117 reviewed `highway` line objects in both runs; canonical ID multisets matched. First observed wall times were 89.179 s (minimal GDAL) and 126.289 s (audited targeted). These figures are descriptive, not same-workload speed parity. A separate spatial-index A/B experiment found no stable speedup; default is retained.

The benchmark PBF and derived large GeoPackages are **not redistributed**. Their license obligations and the application MIT source license are distinct. See OSM_ATTRIBUTION_AND_ODBL.md.
