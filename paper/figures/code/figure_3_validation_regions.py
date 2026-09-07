from pathlib import Path

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Input data
# ---------------------------------------------------------------------
regions = pd.read_csv(DATA / "Figure_3_validation_regions.csv")
world = gpd.read_file(DATA / "naturalearth_lowres" / "naturalearth_lowres.shp")
world = world.to_crs("EPSG:4326")

# ---------------------------------------------------------------------
# Build a coastline-only basemap
# Dissolve all land polygons so that internal country borders disappear.
# The boundary of the dissolved landmass is then the coastline layer.
# ---------------------------------------------------------------------
land = world[["geometry"]].dissolve()
coastline = land.boundary

# ---------------------------------------------------------------------
# Theme styles
# ---------------------------------------------------------------------
theme_styles = {
    "power": {
        "marker": "o",
        "facecolor": "#f2c14e",
        "edgecolor": "#6b5600",
    },
    "aeroway": {
        "marker": "s",
        "facecolor": "#4ea5d9",
        "edgecolor": "#1d4f73",
    },
    "pipeline": {
        "marker": "^",
        "facecolor": "#ef8354",
        "edgecolor": "#8a3f1e",
    },
}

def get_alignment(lon, label_x):
    return "left" if label_x >= lon else "right"

# ---------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12.0, 4.15))

# Light land fill
land.plot(ax=ax, facecolor="#f7f7f7", edgecolor="none", zorder=1)

# Coastline only
coastline.plot(ax=ax, color="#8a8a8a", linewidth=0.55, zorder=2)

# Axes extent
ax.set_xlim(-150, 155)
ax.set_ylim(-5, 75)

# Axis labels
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")

# Light grid
ax.grid(True, linewidth=0.35, color="#d7d7d7", alpha=0.7)
ax.set_axisbelow(True)

# ---------------------------------------------------------------------
# Region markers and annotations
# ---------------------------------------------------------------------
for _, r in regions.iterrows():
    style = theme_styles.get(
        r.theme,
        {
            "marker": "o",
            "facecolor": "#6c757d",
            "edgecolor": "#343a40",
        },
    )

    ax.scatter(
        r.longitude,
        r.latitude,
        s=74,
        marker=style["marker"],
        facecolor=style["facecolor"],
        edgecolor=style["edgecolor"],
        linewidth=0.8,
        zorder=5,
    )

    ax.annotate(
        f"{r.region}\n{r.theme}",
        xy=(r.longitude, r.latitude),
        xytext=(r.label_x, r.label_y),
        textcoords="data",
        fontsize=8.9,
        ha=get_alignment(r.longitude, r.label_x),
        va="center",
        arrowprops=dict(
            arrowstyle="-",
            linewidth=0.65,
            color="#555555",
        ),
        bbox=dict(
            boxstyle="round,pad=0.18",
            fc="white",
            ec="none",
            alpha=0.88,
        ),
        zorder=6,
    )

# ---------------------------------------------------------------------
# Compact legend
# ---------------------------------------------------------------------
legend_order = ["power", "aeroway", "pipeline"]
handles = []

for theme in legend_order:
    style = theme_styles[theme]
    handles.append(
        Line2D(
            [0], [0],
            marker=style["marker"],
            linestyle="",
            markersize=7,
            markerfacecolor=style["facecolor"],
            markeredgecolor=style["edgecolor"],
            label=theme,
        )
    )

ax.legend(
    handles=handles,
    title="Validation theme",
    loc="lower left",
    frameon=True,
    framealpha=0.95,
    facecolor="white",
    edgecolor="#d0d0d0",
    fontsize=8.5,
    title_fontsize=8.8,
)

# Frame styling
for spine in ax.spines.values():
    spine.set_linewidth(0.8)
    spine.set_color("#666666")

fig.tight_layout(pad=0.45)

# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------
fig.savefig(OUT / "Figure_3_validation_regions.png", dpi=600, bbox_inches="tight")
fig.savefig(OUT / "Figure_3_validation_regions.pdf", bbox_inches="tight")
plt.close(fig)