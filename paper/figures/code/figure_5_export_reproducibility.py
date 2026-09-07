from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def draw(data_file: Path, output_dir: Path) -> None:
    data = pd.read_csv(data_file).set_index("Format")
    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 5.25))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5.6)
    ax.axis("off")

    gp = data.loc["GeoPackage"]
    shp = data.loc["Shapefile"]

    cards = [
        (0.35, 2.75, "GeoPackage", "#EAF6F0", "#3C8D6B"),
        (3.35, 2.75, "Shapefile", "#FDF0EC", "#C6533C"),
        (6.35, 5.30, "Repeated-run checks", "#EEF3F8", "#2F75B5"),
    ]
    for x, w, title, fc, ec in cards:
        ax.add_patch(FancyBboxPatch(
            (x, 0.75), w, 4.15,
            boxstyle="round,pad=.04,rounding_size=.08",
            facecolor=fc, edgecolor=ec, linewidth=1.7,
        ))
        ax.text(x + w/2, 4.55, title, ha="center", va="center", fontsize=12, fontweight="bold")

    gpkg = [
        f"{int(gp.Features):,} features",
        "complete tags_json",
        "no field-name truncation observed",
        "no value truncation observed",
        "geometry separated by group",
    ]
    shpf = [
        f"{int(shp.Features):,} features",
        "tags_json not retained",
        "field names mapped",
        f"{int(shp.Attribute_value_truncations)} values truncated",
        "Unicode reader-dependent",
    ]
    checks = [
        "same input SHA-256",
        "same profile SHA-256",
        "same matched-object counts",
        "same OSM ID sets",
        "same layer / feature counts",
        "SQLite / GPKG integrity: ok",
    ]

    for i, text in enumerate(gpkg):
        ax.text(0.65, 4.05 - i*0.62, "✓ " + text, fontsize=8.8, color="#234F3C", va="center")
    for i, text in enumerate(shpf):
        symbol = "✓ " if i == 0 else "△ "
        ax.text(3.65, 4.05 - i*0.62, symbol + text, fontsize=8.8, color="#7A2E22", va="center")
    for i, text in enumerate(checks):
        ax.text(6.72, 4.08 - i*0.53, "✓ " + text, fontsize=8.9, color="#28313C", va="center")

    fig.tight_layout(pad=0.35)
    fig.savefig(output_dir / "Figure_5_export_reproducibility.png", dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(output_dir / "Figure_5_export_reproducibility.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data/Figure_5_export_audit_data.csv")
    parser.add_argument("--output-dir", type=Path, default=root / "output")
    args = parser.parse_args()
    draw(args.data, args.output_dir)
