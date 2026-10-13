> **Historical development document (pre-v0.4.2).** Refer to README.md and RELEASE_NOTES_v0.4.2.md for current instructions.

# Round-two targeted highway extraction – experimental dev1

## Purpose and scientific scope

The `quick-extract` command is a **new, limited CLI experiment** motivated by
reviewer testing. It does not replace `scan → classify → export`.

Its audited result is bound to an input SHA-256, profile SHA-256, exact GDAL
`lines` layer, canonical `way/{osm_id}`, reviewed one-to-one `highway` category,
and original tag JSON. The GDAL `-sql` predicate filters written records, but
it **does not guarantee that GDAL avoids parsing the PBF**; runtime and resource
usage must be determined empirically. The full tag inventory and deterministic
pre-export quality audit are intentionally omitted.

Only a fail-closed, non-overlapping whitelist of `highway` values defined by
`equals` or `in` rules on `source_layer: ["lines"]` is supported. GPKG only;
no GUI integration; no arbitrary `all/any/none` rules. Do not claim feature
parity for other source layers, other keys, or other profiles.

## Windows smoke test (Anaconda Prompt)

Download the complete dev1 source into a **new directory**. The existing
v0.4.1 release and v0.4.2.dev0 workspace should be left unchanged.

```bat
cd /d D:\OSM\OSM_Round2_Targeted_Dev_Workspace_v0.4.2dev1
conda activate osm-scientific-converter-phase3
python -m pip install -e .
python -m pytest -q
osm-sci --version

osm-sci quick-extract examples\round2_roads_small.osm --rules examples\round2_road_extraction_rules.json --output round2_quick_roads.gpkg

ogrinfo -so -al round2_quick_roads.gpkg

python tools\round2_compare_osm_ids.py --converter round2_quick_roads.gpkg --baseline round2_baseline.gpkg --source-layer lines --compare-geometries --out round2_quick_vs_baseline.json
```

`round2_baseline.gpkg` comes from the prior validated dev0 experiment, in the
old directory. If unavailable, create it in the new root first:

```bat
python tools\round2_direct_gdal_baseline.py --input examples\round2_roads_small.osm --rules examples\round2_road_extraction_rules.json --base-config src\osm_scientific_converter\resources\osmconf.ini --output round2_baseline.gpkg --report round2_baseline_report.json
```

The quick-extract command must write a GPKG and the sidecar
`round2_quick_roads.gpkg.audit.json` with an actual `feature_count=4`.
Do **not** assume PASS until the local comparator confirms object identity,
geometry type, CRS and geometric equality.

## Medium/large-file experiment

Only after the small-test PASS, supply a known real `.osm.pbf` file:

```bat
osm-sci quick-extract "D:\DATA\EXTRACT.osm.pbf" --rules examples\round2_road_extraction_rules.json --output roads_targeted.gpkg
```

Preserve the resulting `.gpkg.audit.json`. Collect:
- exact PBF filename, SHA-256 and extraction date;
- CPU, RAM, storage and GDAL version;
- total duration (hash, GDAL selective import, tagging/provenance, copying);
- peak RSS (requires independent monitoring on Windows);
- selected feature count and output size;
- direct GDAL baseline for **same input**;
- canonical IDs and geometry-type histogram comparison.

For >10,000 objects, omit the `--compare-geometries` flag from the existing
comparison script. Run representative sample geometry checks separately.

For publication, record at least three repetitions after a controlled warm-up
and report medians, ranges and cold/warm-cache conditions. The minimum GDAL
baseline and the audited targeted mode do not implement exactly the same
output schema, so runtime is a descriptive comparison, not direct evidence
that one tool is intrinsically faster at identical work.

## Known caveats

- The GDAL OSM driver can still read most of the PBF to reconstruct ways;
  SQL `WHERE highway IN (...)` filters output and is not promised upstream
  byte-level prefiltering.
- `all_tags` must include the highway key. If not, extraction fails closed.
- The JSON sidecar is a limited provenance record, not a quality certificate.
- Windows packaging and actual large-data GDAL performance are **not**
  validated in the present container.
- This is experimental developer code; do not push to the public GitHub
  `main` branch or replace the validated `v0.4.1` Release.
