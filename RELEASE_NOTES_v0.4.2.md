# OSM Scientific Converter v0.4.2

OSM Scientific Converter v0.4.2 is a software release providing updated source code and a Windows x64 standalone application for reproducible thematic preparation of OpenStreetMap data.

## Changes relative to v0.4.1

- Added strict classification restrictions using exact GDAL source-layer names.
- Introduced an optional reviewed highway quick-extraction workflow in the GUI and CLI, without requiring the complete inventory scan.
- Improved GUI feature selection, attribute inspection, result separation, and progress reporting.
- Improved GeoPackage enrichment through GDAL/OGR for Windows spatial database compatibility.
- Added support for headless quick-extraction subprocess execution from the packaged Windows application.
- Retained deferred-RTree optimization as an optional experiment, disabled by default.

## Validation evidence

The v0.4.2 development source tree was previously evaluated with 127 passing automated tests, interactive GUI checks, and a fixed real-data benchmark.

The subsequent Windows build-host validation record reports 133 passing automated tests, together with successful frozen-GUI startup, standard scan/classification/export, and quick-extraction smoke tests.

The final public Windows x64 ZIP was repackaged and its SHA-256 checksum verified. Additional interactive testing of the packaged application was reported by the release maintainer.

These checks document the tested configurations and do not establish universal operating-system compatibility.

## Real-data benchmark

A fixed Brazil Sudeste OSM PBF snapshot dated 2026-09-01 (856,168,766 bytes) was evaluated during development.

The direct-GDAL minimal workflow and the reviewed quick-extraction workflow produced matching canonical OSM ID multisets comprising 2,067,117 highway line objects.

Single measured wall times were 89.179 s and 126.289 s, respectively. Because the workflows have different output and provenance requirements, these measurements do not demonstrate a speed advantage.

Complete geometry and attribute equality across all extracted objects was not established.

## Scientific limitations

The standard workflow and the optional quick-extraction workflow serve different purposes. Quick extraction does not perform the complete tag-vocabulary inventory or full project quality audit.

The software supports reproducible preparation of thematic OSM datasets within explicitly defined data and rule scopes. Its outputs do not independently establish real-world infrastructure completeness or positional accuracy.

Independent clean-Windows-host validation, digital code signing, formal security auditing, and compatibility verification on other operating systems have not been completed.

## Distribution

The v0.4.2 GitHub Release provides the Windows x64 standalone archive and its SHA-256 checksum file.

Users should extract the entire archive and retain the `_internal` directory alongside the executable.

Versioned source code is available from the corresponding Git tag.

## Authors

Qingsong Du, Guoyu Li, Fei Wang, Wei Ma, and Yanhu Mu.

## License and attribution

The source code is distributed under the repository's MIT license. OpenStreetMap data and relevant derived products remain subject to applicable OSM attribution and ODbL obligations. Third-party notices are provided separately.
