from pathlib import Path
import argparse
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def draw(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6.4))
    ax.set_xlim(0, 12); ax.set_ylim(0, 7); ax.axis('off')
    navy='#183153'; blue='#2F75B5'; pale='#EAF2F8'; green='#3C8D6B'; orange='#C76D2A'; gray='#5A6470'

    def box(x,y,w,h,title,lines,fc=pale,ec=blue):
        patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.03,rounding_size=0.08',linewidth=1.5,facecolor=fc,edgecolor=ec)
        ax.add_patch(patch)
        ax.text(x+w/2,y+h-0.25,title,ha='center',va='top',fontsize=10.5,fontweight='bold',color=navy)
        ax.text(x+0.15,y+h-0.65,'\n'.join(lines),ha='left',va='top',fontsize=8.4,color='#263238',linespacing=1.35)

    def arrow(x1,y1,x2,y2,label=None):
        ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=13,linewidth=1.4,color=gray))
        if label:
            ax.text((x1+x2)/2,(y1+y2)/2+0.15,label,ha='center',va='bottom',fontsize=7.5,color=gray)

    box(0.2,4.55,2.0,1.55,'Input snapshot',['.osm or .osm.pbf','SHA-256 and size','environment check'],fc='#F7F9FB')
    box(2.65,4.55,2.25,1.55,'OSM-aware import',['GDAL/OGR reconstruction','points · lines','multilinestrings','multipolygons · relations'])
    box(5.35,4.55,2.25,1.55,'Disk-backed inventory',['streamed tag parsing','SQLite key/value counts','lifecycle inventory','bounded memory'])
    box(8.05,4.55,2.25,1.55,'Versioned classification',['built-in or custom JSON','nested all/any/none','category and rule evidence','profile SHA-256'])
    box(10.55,4.55,1.25,1.55,'Output',['GPKG','GeoJSON','Shapefile'])
    for x1,x2 in [(2.2,2.65),(4.9,5.35),(7.6,8.05),(10.3,10.55)]: arrow(x1,5.32,x2,5.32)
    box(2.0,1.55,2.4,1.7,'Quality and loss audit',['deterministic category × geometry sampling','category-applicable expected fields','geometry warnings and parse failures','format-specific truncation report'],fc='#FDF4E8',ec=orange)
    box(4.8,1.55,2.4,1.7,'Project provenance',['input/profile/config hashes','resolved rules and selections','software and dependency versions','atomic logs and feedback'],fc='#EAF6F0',ec=green)
    box(7.6,1.55,2.4,1.7,'User interfaces',['PySide6 five-step desktop GUI','CLI with the same scientific core','paginated inventory queries','background tasks and cancellation'],fc='#EEF0FA',ec='#5967A9')
    for x in [3.2,6.0,8.8]: arrow(x,4.55,x,3.25)
    ax.text(6,0.55,'All stages operate on a dated local snapshot; no online refresh, silent reprojection, or automatic geometry repair is performed.',ha='center',va='center',fontsize=8.5,color=gray)
    fig.tight_layout()
    fig.savefig(output_dir/'Figure_1_architecture.png',dpi=600,bbox_inches='tight',facecolor='white')
    fig.savefig(output_dir/'Figure_1_architecture.pdf',bbox_inches='tight',facecolor='white')
    plt.close(fig)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'output')
    draw(parser.parse_args().output_dir)
