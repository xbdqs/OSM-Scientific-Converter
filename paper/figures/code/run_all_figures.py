from pathlib import Path
import subprocess, sys
HERE = Path(__file__).resolve().parent
scripts = [
    "figure_1_architecture.py",
    "figure_2_actual_english_gui.py",
    "figure_3_validation_regions.py",
    "figure_4_thematic_examples.py",
    "figure_5_export_reproducibility.py",
    "figure_6_performance.py",
]
for s in scripts:
    print(f"Running {s}...")
    subprocess.run([sys.executable, str(HERE / s)], check=True)
print("All manuscript figures generated.")
