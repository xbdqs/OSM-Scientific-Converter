# Revised manuscript figures and reproducible code

This directory matches the revised SoftwareX manuscript SOFTX-D-26-01000.

## Figure numbering

1. `Figure_1_architecture` - software architecture and evidence flow.
2. `Figure_2_actual_English_GUI_workflow` - five-step English GUI captured from the packaged v0.4.1 Windows application during the Berlin power workflow.
3. `Figure_3_validation_regions` - overview of the four validation regions. Natural Earth public-domain country boundaries are used only as geographic background; markers indicate representative locations, not exact Geofabrik extract boundaries.
4. `Figure_4_thematic_examples` - major thematic categories in Berlin power, South Korea aeroway and New York pipeline cases.
5. `Figure_5_export_reproducibility` - observed Berlin export audit and repeated-run reproducibility checks.
6. `Figure_6_performance` - complete-workflow time and peak resident memory.

## Reproduction

Run:

```bash
python code/run_all_figures.py
```

Python dependencies used by the figure scripts include matplotlib, pandas, Pillow and geopandas. The Natural Earth low-resolution shapefile required for Figure 3 is bundled under `data/naturalearth_lowres/` for reproducibility.
