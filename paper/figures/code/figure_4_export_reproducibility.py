from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

def draw(data_file: Path, output_dir: Path) -> None:
    data=pd.read_csv(data_file).set_index('Format')
    output_dir.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(12,5.8)); ax.set_xlim(0,12); ax.set_ylim(0,6); ax.axis('off')
    cards=[(0.35,'GeoPackage','#EAF6F0','#3C8D6B'),(3.25,'Shapefile','#FDF0EC','#C6533C')]
    for x,title,fc,ec in cards:
        ax.add_patch(FancyBboxPatch((x,1.0),2.55,4.05,boxstyle='round,pad=.05,rounding_size=.08',facecolor=fc,edgecolor=ec,linewidth=1.8))
        ax.text(x+1.275,4.72,title,ha='center',fontsize=12,fontweight='bold')
    gp=data.loc['GeoPackage']; shp=data.loc['Shapefile']
    gpkg=[f"{int(gp.Features):,} features written",'complete tags_json retained',f"{gp.Field_name_truncations} field-name truncations",f"{gp.Attribute_value_truncations} attribute truncations",'mixed geometry separated by group']
    shpf=[f"{int(shp.Features):,} features written",'complete tags_json not retained',f"field names: {shp.Field_name_truncations}",f"{shp.Attribute_value_truncations} attribute values truncated",'Unicode support depends on reader']
    for i,t in enumerate(gpkg): ax.text(.58,4.2-i*.58,'✓ '+t,fontsize=9,color='#234F3C')
    for i,t in enumerate(shpf): ax.text(3.48,4.2-i*.58,('✓ ' if i==0 else '⚠ ')+t,fontsize=9,color='#7A2E22')
    ax.add_patch(FancyBboxPatch((6.35,1.0),5.3,4.05,boxstyle='round,pad=.05,rounding_size=.08',facecolor='#EEF3F8',edgecolor='#2F75B5',linewidth=1.8))
    ax.text(9.0,4.72,'Repeated-run checks',ha='center',fontsize=12,fontweight='bold')
    checks=['identical input SHA-256','identical profile SHA-256','equal matched-object counts','equal OSM ID sets','equal export layer/feature counts','SQLite and GPKG integrity = ok']
    for i,t in enumerate(checks): ax.text(6.65,4.18-i*.5,'✓ '+t,fontsize=9,color='#28313C')
    ax.text(9.0,1.35,'Reproducibility is assessed from hashes, object sets, counts, layers, and integrity checks.',ha='center',fontsize=7.7,color='#5A6470')
    fig.tight_layout()
    fig.savefig(output_dir/'Figure_4_export_reproducibility.png',dpi=600,bbox_inches='tight',facecolor='white')
    fig.savefig(output_dir/'Figure_4_export_reproducibility.pdf',bbox_inches='tight',facecolor='white')
    plt.close(fig)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(); p.add_argument('--data',type=Path,default=root/'data/Figure_4_export_audit_data.csv'); p.add_argument('--output-dir',type=Path,default=root/'output')
    a=p.parse_args(); draw(a.data,a.output_dir)
