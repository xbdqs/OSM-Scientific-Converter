# OSM Scientific Converter v0.4.2 — release source candidate

## Changes relative to v0.4.1

- Strict classification restriction by exact GDAL source-layer name (`--source-layer lines` excludes multilinestrings).
- Experimental reviewed `highway`/`lines` quick workflow in CLI and GUI, without a full scan, limited preview and scope-labelled audit.
- GUI output/quick result separation, geometry selection tolerances, feature tags and progress semantics.
- GeoPackage enrichment uses GDAL/OGR to preserve spatial-trigger compatibility on Windows.
- Explicitly optional deferred-RTree experiment remains off by default; three A/B comparisons did not establish a stable speed advantage.
- Packaged GUI re-enters a constrained `--headless-cli quick-extract` subcommand so the frozen Windows EXE can run its quick-extraction subprocess.

## Testable evidence and limits

- Windows v0.4.2.dev1 source tree was user-tested: 127 automated tests following GUI changes, real four-object selection and interactive tags, and one fixed real PBF benchmark. These tests are **pre-release** and do not certify rebuilt 0.4.2 binaries.
- Fixed 2026-09-01 Brazil Sudeste PBF (856,168,766 bytes, SHA-256 e850eeafc2ec1d94d5b6014b89b923f239a95415e663301cbe21907fa805dfc8) produced 2,067,117 matching `highway` lines in both direct-GDAL minimal mode and audited quick mode (canonical ID multi-set equality). Same-machine single measured wall times: 89.179 s and 126.289 s; **not equivalent output/provenance workloads**, no speed superiority claim.
- The full workflow and optional quick workflow differ deliberately; quick mode lacks the complete tag-vocabulary scan and full project quality audit. Complete 2M+ feature geometry and all-attribute equality were not established.

## Release gating

This archive provides versioned source and build inputs. A **standalone Windows x64 executable must be built and verified on Windows** (including frozen GUI + headless quick smoke) before labeling its binary a validated release. The archive itself does not imply any GitHub upload, Windows signing, DOI, publisher review or compatibility verification on other systems.

Before publishing, verify the `CITATION.cff` author identity, affiliations and date; do not invent author IDs. Confirm redistribution rights for OSM-derived examples, maps and dependencies.
