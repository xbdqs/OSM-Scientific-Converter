from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "source_panels"
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

PANELS = [
    ("a", "Step 1. Input and environment", SRC / "Figure_2a_step1_input_environment.png"),
    ("b", "Step 2. Data overview", SRC / "Figure_2b_step2_data_overview.png"),
    ("c", "Step 3. Feature selection", SRC / "Figure_2c_step3_feature_selection.png"),
    ("d", "Step 4. Preview and quality checks", SRC / "Figure_2d_step4_preview_quality.png"),
    ("e", "Step 5. Export", SRC / "Figure_2e_step5_export.png"),
]

CANVAS_W = 2400
MARGIN = 28
GAP = 24
LABEL_H = 54
BORDER = 2
PAGE_BG = (247, 247, 247)
PANEL_BG = (255, 255, 255)
BORDER_COLOR = (170, 170, 170)
TEXT_COLOR = (22, 22, 22)
FONT_PATHS = [
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
]
font = None
for fp in FONT_PATHS:
    if fp.exists():
        font = ImageFont.truetype(str(fp), 29)
        break
if font is None:
    font = ImageFont.load_default()

half_w = (CANVAS_W - 2 * MARGIN - GAP) // 2
# All source screenshots have approximately the same 1.86:1 aspect ratio.
source_ratio = 1918 / 1030
half_img_h = round((half_w - 2 * BORDER) / source_ratio)
half_panel_h = LABEL_H + half_img_h + 2 * BORDER
full_w = CANVAS_W - 2 * MARGIN
full_img_h = round((full_w - 2 * BORDER) / source_ratio)
full_panel_h = LABEL_H + full_img_h + 2 * BORDER
CANVAS_H = 2 * MARGIN + 2 * half_panel_h + full_panel_h + 2 * GAP

canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), PAGE_BG)
draw = ImageDraw.Draw(canvas)

positions = [
    (MARGIN, MARGIN, half_w, half_panel_h),
    (MARGIN + half_w + GAP, MARGIN, half_w, half_panel_h),
    (MARGIN, MARGIN + half_panel_h + GAP, half_w, half_panel_h),
    (MARGIN + half_w + GAP, MARGIN + half_panel_h + GAP, half_w, half_panel_h),
    (MARGIN, MARGIN + 2 * half_panel_h + 2 * GAP, full_w, full_panel_h),
]

for (letter, title, image_path), (x, y, panel_w, panel_h) in zip(PANELS, positions):
    screenshot = Image.open(image_path).convert("RGB")
    target_w = panel_w - 2 * BORDER
    target_h = panel_h - LABEL_H - 2 * BORDER
    screenshot = screenshot.resize((target_w, target_h), Image.Resampling.LANCZOS)

    draw.rounded_rectangle(
        [x, y, x + panel_w, y + panel_h],
        radius=7,
        fill=PANEL_BG,
        outline=BORDER_COLOR,
        width=2,
    )
    draw.text((x + 14, y + 10), f"({letter}) {title}", fill=TEXT_COLOR, font=font)
    canvas.paste(screenshot, (x + BORDER, y + LABEL_H + BORDER))

png_path = OUT / "Figure_2_actual_English_GUI_workflow.png"
canvas.save(png_path, dpi=(300, 300))

# Image-only PDF preserves the exact GUI pixels and panel layout.
rgb = canvas.convert("RGB")
pdf_path = OUT / "Figure_2_actual_English_GUI_workflow.pdf"
rgb.save(pdf_path, "PDF", resolution=300.0)

print(png_path)
print(pdf_path)
