from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPTS = [
    "figure_1_architecture.py",
    "figure_2_actual_english_gui.py",
    "figure_3_thematic_examples.py",
    "figure_4_export_reproducibility.py",
    "figure_5_performance.py",
]
for script in SCRIPTS:
    subprocess.run([sys.executable, str(HERE / script)], check=True)
print("All five manuscript figures were generated successfully.")
