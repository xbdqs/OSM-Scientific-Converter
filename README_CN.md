# OSM Scientific Converter v0.4.2

软件提供两条流程：

1. **完整审计流程**：五步桌面 GUI 或 `scan → classify → export`，包括标签库存、规则分类、有限预览、分层抽样质量检查及多格式导出。支持 power、pipeline、aeroway 主题。
2. **道路快速提取**：Step 1 的 `Quick roads (no scan)` 或 CLI `quick-extract`。严格限定 GDAL `lines` 图层、13种经过审查的 `highway` 值和4类道路，只输出 GPKG 及侧车审计 JSON。该模式不建立完整标签库存、也不开展完整的导出前质量审计。GUI 地图仅预览前400条已导出线段，不能据此判断空间完整性。

## 安装与运行

在包含 GDAL Python 绑定、`ogr2ogr` 和 PySide6 的 conda 环境中：

```bat
python -m pip install -e .[test]
python -m pytest -q
osm-sci --version
osm-sci-gui
osm-sci quick-extract examples\round2_roads_small.osm --rules examples\round2_road_extraction_rules.json --output quick_example.gpkg
```

**发布范围**：源码包和 wheel 可以独立发布；Windows 独立 EXE 必须用 `tools\build_windows_v042.bat` 在 Windows 实机重新构建，并验证冻结程序的 GUI、扫描导出和快速道路提取，不能因为源代码测试通过便宣称 EXE 已验收。

参见 `RELEASE_NOTES_v0.4.2.md`、`RELEASE_VALIDATION_CHECKLIST_CN.md`、`QUICK_START_CN.md`、`OSM_ATTRIBUTION_AND_ODBL.md`。`validation/round2_v042` 是开发版本的历史实测证据，不是 v0.4.2 冻结包的新性能测量。
