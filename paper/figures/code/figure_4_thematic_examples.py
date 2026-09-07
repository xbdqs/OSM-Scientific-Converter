from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

CASES=[
    ('Berlin: power','Berlin power',['generator','substation','tower','cable','pole','lifecycle']),
    ('South Korea: aeroway','South Korea aeroway',['taxiway','helipad','parking position','navigation aid','hangar','gate']),
    ('New York: pipeline','New York pipeline',['storage candidate','pipeline','water','gas','transmission','valve']),
]

def draw(data_file: Path, output_dir: Path) -> None:
    df=pd.read_csv(data_file)
    output_dir.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,3,figsize=(13.2,5.3))
    for panel,(ax,(title,case,cats)) in enumerate(zip(axes,CASES)):
        part=df[df['Case'].eq(case)].set_index('Category')
        values=np.array([int(part.loc[c,'Matched_objects']) for c in cats])
        labels=np.array(cats); order=np.argsort(values)
        ax.barh(labels[order],values[order])
        for i,v in enumerate(values[order]): ax.text(v,i,f' {v:,}',va='center',fontsize=8)
        ax.text(-0.12,1.04,f'({chr(97+panel)})',transform=ax.transAxes,fontweight='bold')
        ax.set_title(title,fontweight='bold'); ax.set_xlabel('Matched objects'); ax.grid(axis='x',alpha=.25)
        ax.spines[['top','right','left']].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_dir/'Figure_4_thematic_examples.png',dpi=600,bbox_inches='tight',facecolor='white')
    fig.savefig(output_dir/'Figure_4_thematic_examples.pdf',bbox_inches='tight',facecolor='white')
    plt.close(fig)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(); p.add_argument('--data',type=Path,default=root/'data/Figure_4_thematic_category_data.csv'); p.add_argument('--output-dir',type=Path,default=root/'output')
    a=p.parse_args(); draw(a.data,a.output_dir)
