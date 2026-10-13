# v0.4.2 Windows 操作说明

**先确认** `tools/build_windows_v042.bat` 生成的打包验收报告 PASS，独立版 ZIP 才适合分发。保持 EXE 与 `_internal` 文件夹的相对位置。

- 完整流程：打开 `OSMScientificConverter_v0.4.2.exe`，Step 1 选择 `examples/sample_infrastructure.osm` 和新项目目录，检查环境并开始扫描；Step 3 选择 `power` 并分类；Step 4 预览与抽样质量核查；Step 5 导出。
- 快速道路流程：在 Step 1 点击 `Quick roads (no scan)...`，选择 `examples/round2_roads_small.osm`，将输出设在可写目录新建 `quick_roads.gpkg`，核对规则 `reviewer_roads_lines_v1.json` 并开始。Step 4 可浏览有限的道路样本并点击单条线查看标签；Step 5 显示已创建文件和受限审计范围，无需再次点击导出。
- 快速模式仍可能读取整个 PBF 以重建几何，不代表完整道路网络，也没有完整库存或质量审计。完整 OSM 快照、几何 GPKG 不随代码包分发。

源代码用户请先执行 `python -m pytest -q`。详见 `RELEASE_VALIDATION_CHECKLIST_CN.md`。
