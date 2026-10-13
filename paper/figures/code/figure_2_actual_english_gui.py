from pathlib import Path
import argparse
from PIL import Image, ImageDraw, ImageFont


def font(size: int, bold: bool=False):
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',
    ]
    for path in candidates:
        try: return ImageFont.truetype(path,size)
        except OSError: pass
    return ImageFont.load_default()


def build(screenshots: Path, output: Path) -> None:
    names=['02_selection.png','03_preview_quality.png','04_export.png']
    missing=[name for name in names if not (screenshots/name).is_file()]
    if missing:
        raise FileNotFoundError(f'Missing actual GUI screenshots: {missing}. Run the English packaged-GUI acceptance workflow first.')
    imgs=[Image.open(screenshots/name).convert('RGB') for name in names]
    target_w=1500
    resized=[]
    for im in imgs:
        ratio=target_w/im.width
        resized.append(im.resize((target_w,int(im.height*ratio)),Image.Resampling.LANCZOS))
    margin=40; label_h=58
    total_h=margin+sum(im.height+label_h+margin for im in resized)
    canvas=Image.new('RGB',(target_w+2*margin,total_h),'white')
    draw=ImageDraw.Draw(canvas)
    labels=['(a) Feature selection and validated rules','(b) Bounded spatial preview and stratified quality checks','(c) Export settings, audit summary, and project evidence']
    y=margin
    for im,label in zip(resized,labels):
        draw.text((margin,y),label,font=font(28,True),fill=(24,49,83))
        y+=label_h
        canvas.paste(im,(margin,y))
        y+=im.height+margin
    output.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(output,dpi=(300,300))
    canvas.save(output.with_suffix('.pdf'),'PDF',resolution=300)

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Assemble Figure 2 from screenshots captured by the actual English GUI build.')
    p.add_argument('--screenshots',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); build(a.screenshots,a.output)
