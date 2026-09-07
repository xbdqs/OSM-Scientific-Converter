from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def draw(data_file: Path, output_dir: Path) -> None:
    df=pd.read_csv(data_file)
    output_dir.mkdir(parents=True,exist_ok=True)
    labels=[f"{r.Region}\n{r.Profile}" for r in df.itertuples()]
    x=np.arange(len(df))
    fig,axes=plt.subplots(1,2,figsize=(12.8,5.4))
    axes[0].bar(x,df['Total_time_min'])
    for i,v in enumerate(df['Total_time_min']): axes[0].text(i,v+max(df['Total_time_min'])*.02,f'{v:.1f}',ha='center',fontsize=8)
    axes[0].set_xticks(x,labels); axes[0].set_ylabel('Complete workflow time (min)'); axes[0].set_title('(a) Regional workflow time',fontweight='bold'); axes[0].grid(axis='y',alpha=.25); axes[0].spines[['top','right']].set_visible(False)
    axes[1].bar(x,df['Peak_RSS_MiB'])
    for i,v in enumerate(df['Peak_RSS_MiB']): axes[1].text(i,v+8,f'{v:.1f}',ha='center',fontsize=8)
    axes[1].set_xticks(x,labels); axes[1].set_ylabel('Peak resident memory (MiB)'); axes[1].set_title('(b) Complete-workflow peak memory',fontweight='bold'); axes[1].grid(axis='y',alpha=.25); axes[1].spines[['top','right']].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_dir/'Figure_6_performance.png',dpi=600,bbox_inches='tight',facecolor='white')
    fig.savefig(output_dir/'Figure_6_performance.pdf',bbox_inches='tight',facecolor='white')
    plt.close(fig)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(); p.add_argument('--data',type=Path,default=root/'data/Figure_6_performance_data.csv'); p.add_argument('--output-dir',type=Path,default=root/'output')
    a=p.parse_args(); draw(a.data,a.output_dir)
