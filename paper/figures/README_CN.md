# 论文全部图件与绘图代码

本目录与 SoftwareX 稿件中的图号严格一致：

1. `Figure_1_architecture`：软件架构和证据流；
2. `Figure_2_actual_English_GUI_workflow`：Berlin 项目真实英文 GUI 五步工作流；
3. `Figure_3_thematic_examples`：Berlin power、South Korea aeroway 和 New York pipeline 的主要类别；
4. `Figure_4_export_reproducibility`：Berlin GeoPackage/Shapefile 信息保留与重复运行检查；
5. `Figure_5_performance`：四个区域案例的完整工作流时间和峰值内存。

目录：

- `code/`：每幅图的独立代码，以及 `run_all_figures.py`；
- `data/`：Figure 3-5 的绘图数据；
- `source_panels/`：Figure 2 的五张真实软件截图；
- `output/`：每幅图的 PNG 和 PDF。

依赖：Python、Pillow、pandas、numpy 和 matplotlib。

运行：

```bash
python code/run_all_figures.py
```

Figure 2 的文件夹结果截图未放入主图，因为它们不属于五步 GUI 工作流，并且不能代替要素数、完整性检查和导出审计。
