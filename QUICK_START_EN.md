# Windows standalone quick start

1. Extract the entire Windows ZIP. Keep the executable and `_internal` directory together.
2. Run `OSMScientificConverter_v0.4.1.exe`.
3. In Step 1, select `examples/sample_infrastructure.osm` and choose a new project directory.
4. Inspect the input and environment, then run the scan.
5. In Step 3, select the `power` profile and run classification.
6. In Step 4, load the preview and run the quality checks.
7. In Step 5, select GeoPackage and export.
8. Compare the output with `examples/expected_output_summary.json` and inspect `classification_summary.json` and `exports/export_audit.json`.

The field selector controls profile attributes only. Ten traceability fields are always retained. Shapefile exports must be interpreted together with `shapefile_field_mapping.csv` and `shapefile_loss_report.json`.
