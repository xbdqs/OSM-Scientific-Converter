# Scientific scope and related OSM tools

OSM Scientific Converter does **not** claim that filtering OpenStreetMap data is a new operation. Existing tools already provide mature import, conversion, query, database-loading, history, and analysis capabilities.

| Tool/workflow | Primary role | Relationship to OSM Scientific Converter |
|---|---|---|
| GDAL OSM driver | Reads OSM XML/PBF and exposes five logical OSM layers | Used as the low-level reconstruction engine; not replaced. |
| osm2pgsql | Imports OSM into PostgreSQL/PostGIS | Better suited to persistent database/server and many very-large/planet-scale workflows. |
| Osmosis / osmconvert | Command-line file/change processing | Mature deterministic file-processing building blocks. |
| QuickOSM | QGIS interface for Overpass and local OSM workflows | Complementary interactive extraction; the present project adds snapshot-bound inventory, profile hashing, provenance, process audit, and format-loss reporting. |
| OSMnx | Python research software for OSM networks/features | Demonstrates the value of standardized programmatic OSM research workflows; its primary scientific focus differs from this local audit-oriented converter. |
| OSM2CDR | Online conversion service | Broad multi-format conversion; not a local snapshot-bound semantic-project audit. |
| ohsome | Historical OSM access and statistics | Complementary temporal/history service; not a substitute for inventorying the exact local snapshot supplied to a study. |
| OSM Scientific Converter | Local desktop + CLI project | Converts a dated local snapshot into an audited thematic research dataset with inspectable semantic decisions. |

## Scientific problem addressed

For a fixed local OSM snapshot, a reproducible thematic dataset requires more than an executable filter. The workflow must preserve:

1. **Data provenance:** input bytes/hash and OSM source representation;
2. **Semantic provenance:** observed vocabulary and the rules used to interpret heterogeneous tags/lifecycle states; and
3. **Computational/export provenance:** software version, configuration, checks, schema transformation, and observed output loss.

This framing follows the broader geospatial reproducibility emphasis on transparent data acquisition, executable workflows, provenance, version control, and open software. Relevant peer-reviewed context used in the manuscript includes:

- Schlögl M, Waltersdorfer L, Regner P, Siposova A, Brenning A. *Overcoming barriers to reproducibility in geoscientific data analysis: Challenges and practical implementation strategies.* Environmental Modelling & Software. 2026;200:106962. https://doi.org/10.1016/j.envsoft.2026.106962
- Fu X, Liu L, Guan WW, Kalra Y, Bao S, Kötter T, Sturm K. *Advancing replicable and reproducible GIScience: an approach with KNIME.* Cartography and Geographic Information Science. 2026;53(3):270-290. https://doi.org/10.1080/15230406.2024.2446556

SQLite, JSON, GDAL and the GUI are implementation mechanisms rather than scientific novelties by themselves. Their value here is the preservation of the evidence linking a dated input to a thematic output.

## Validation boundary

The software validates extraction behavior, data integrity, reproducibility, and observed export transformations. It does **not** establish physical infrastructure completeness, positional accuracy, or universal thematic correctness of OSM. Those questions require independent domain/ground-truth validation appropriate to the downstream study.
