# Windows 独立版快速开始

1. 完整解压 ZIP；不要只复制 EXE，也不要移动 `_internal`。
2. 双击 `OSMScientificConverter_v0.4.1.exe`。
3. 在 Step 1 选择 `examples/sample_infrastructure.osm`，并选择一个不存在的新工程目录。
4. 单击环境/输入检查，然后运行扫描；示例很小，应快速完成。
5. 在 Step 3 选择 `power`，运行分类。
6. 在 Step 4 加载预览并运行质量检查。
7. 在 Step 5 选择 GPKG 和输出路径后导出。
8. 将结果与 `examples/expected_output_summary.json` 核对，并查看工程目录中的 `classification_summary.json` 与 `exports/export_audit.json`。

真实 PBF 可能需要较多磁盘和时间。运行前应保留足够临时/工程空间；不要把输出目录放在只读目录。若失败，保留界面日志和生成的最小化反馈 ZIP。反馈包不应包含原始 OSM、几何数据库或完整 tags。

字段勾选仅控制 profile 属性；十个追溯字段始终保留。Shapefile 导出后必须同时检查 `shapefile_field_mapping.csv` 和 `shapefile_loss_report.json`。
