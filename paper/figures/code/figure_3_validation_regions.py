from pathlib import Path
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

regions = pd.read_csv(DATA / "Figure_3_validation_regions.csv")
world = gpd.read_file(DATA / "naturalearth_lowres" / "naturalearth_lowres.shp")

fig, ax = plt.subplots(figsize=(12.0, 4.15))
world.plot(ax=ax, facecolor="#f4f4f4", edgecolor="#b7b7b7", linewidth=0.5)
ax.set_xlim(-150, 155)
ax.set_ylim(-5, 75)
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.grid(True, linewidth=0.4, alpha=0.28)

# Keep the map itself concise: region and validation theme only.
for _, r in regions.iterrows():
    ax.scatter(r.longitude, r.latitude, s=66, zorder=5)
    label = f"{r.region}\n({r.theme})"
    ax.annotate(
        label,
        xy=(r.longitude, r.latitude),
        xytext=(r.label_x, r.label_y),
        textcoords="data",
        fontsize=9.2,
        ha="left" if r.label_x > r.longitude else "right",
        va="center",
        arrowprops=dict(arrowstyle="-", linewidth=0.65, color="#444444"),
    )

fig.tight_layout(pad=0.4)
fig.savefig(OUT / "Figure_3_validation_regions.png", dpi=600, bbox_inches="tight")
fig.savefig(OUT / "Figure_3_validation_regions.pdf", bbox_inches="tight")
plt.close(fig)
