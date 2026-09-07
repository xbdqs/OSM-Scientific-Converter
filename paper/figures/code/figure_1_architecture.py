from pathlib import Path
import argparse
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def draw(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 5.45))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.15)
    ax.axis("off")

    navy = "#183153"
    blue = "#2F75B5"
    pale = "#EAF2F8"
    green = "#3C8D6B"
    orange = "#C76D2A"
    gray = "#5A6470"

    def box(x, y, w, h, title, lines, fc=pale, ec=blue):
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.03,rounding_size=0.08",
            linewidth=1.45, facecolor=fc, edgecolor=ec,
        )
        ax.add_patch(patch)
        ax.text(
            x + w / 2, y + h - 0.24, title,
            ha="center", va="top", fontsize=10.1,
            fontweight="bold", color=navy,
        )
        ax.text(
            x + 0.15, y + h - 0.62, "\n".join(lines),
            ha="left", va="top", fontsize=8.05,
            color="#263238", linespacing=1.28,
        )

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle="-|>",
            mutation_scale=12, linewidth=1.35, color=gray,
        ))

    # Primary workflow
    box(0.18, 4.15, 1.95, 1.45, "Input snapshot",
        [".osm / .osm.pbf", "SHA-256 + size", "environment"] , fc="#F7F9FB")
    box(2.48, 4.15, 2.12, 1.45, "OSM-aware import",
        ["GDAL/OGR reconstruction", "five logical OSM layers", "object provenance"])
    box(4.96, 4.15, 2.15, 1.45, "Disk-backed inventory",
        ["streamed tag parsing", "SQLite key/value counts", "lifecycle inventory"])
    box(7.47, 4.15, 2.22, 1.45, "Versioned classification",
        ["built-in / custom JSON", "nested rule logic", "profile SHA-256"])
    box(10.08, 4.15, 1.68, 1.45, "Output",
        ["GeoPackage", "GeoJSON", "Shapefile"])

    for x1, x2 in [(2.13, 2.48), (4.60, 4.96), (7.11, 7.47), (9.69, 10.08)]:
        arrow(x1, 4.88, x2, 4.88)

    # Evidence and interfaces
    box(1.63, 1.05, 2.48, 1.70, "Quality / loss audit",
        ["deterministic sampling", "applicable-field checks", "geometry / parse warnings", "format-loss report"],
        fc="#FDF4E8", ec=orange)
    box(4.76, 1.05, 2.48, 1.70, "Project provenance",
        ["input / profile hashes", "resolved rules / selections", "software versions", "atomic logs / feedback"],
        fc="#EAF6F0", ec=green)
    box(7.89, 1.05, 2.48, 1.70, "User interfaces",
        ["five-step PySide6 GUI", "CLI, same scientific core", "lazy inventory queries", "background execution"],
        fc="#EEF0FA", ec="#5967A9")

    arrow(3.54, 4.15, 3.54, 2.75)
    arrow(6.04, 4.15, 6.04, 2.75)
    arrow(8.58, 4.15, 8.58, 2.75)

    fig.tight_layout(pad=0.35)
    fig.savefig(output_dir / "Figure_1_architecture.png", dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(output_dir / "Figure_1_architecture.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "output")
    draw(parser.parse_args().output_dir)
