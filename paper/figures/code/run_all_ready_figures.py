from pathlib import Path
import subprocess, sys
root=Path(__file__).resolve().parents[1]
for script in ['figure_1_architecture.py','figure_3_thematic_examples.py','figure_4_performance.py','figure_5_export_reproducibility.py']:
    subprocess.run([sys.executable,str(root/'code'/script)],check=True)
print('Figures 1, 3, 4, and 5 generated. Figure 2 must be generated from actual English GUI screenshots.')
