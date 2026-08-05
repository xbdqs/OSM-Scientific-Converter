# OSM Scientific Converter v0.4.1

OSM Scientific Converter 是面向科研数据准备的可审计 OpenStreetMap 扫描、分类与专题导出软件。它从输入快照动态发现 tag，重建 points、lines、multilinestrings、multipolygons、other_relations 五类图层，以版本化 JSON profile 执行可解释分类，并导出 GPKG、GeoJSON 或 Shapefile。

v0.4.1 是从已冻结 v0.4.0 派生的硬化版本。分类器、规则求值器、扫描器、分类 expression 和分类数据库结构均未改变。三份 v0.4.1 profile 因新增类别适用的期望字段元数据而有意采用新的 SHA-256；不得把这些哈希与 v0.4.0 证据混用。

## 使用边界

- 输入仅为本地 `.osm` 或 `.osm.pbf`；软件不下载或更新 OSM 数据。
- 分类结果仅代表给定输入快照和 profile 规则，不是真实设施完整性的保证。
- 原生输出 CRS 为 EPSG:4326；软件不静默重投影。
- 自动几何修复关闭且未实现，避免无记录地修改科研数据。
- 地图预览最多 2,000 个对象；质量检查采用确定性分层样本，不代表全库几何普查。
- Shapefile 存在字段名、文本宽度和 Unicode 兼容性限制；必须查看导出损失报告。

## 五步 GUI

1. 选择输入和新工程目录，核对 SHA-256 与 GDAL/磁盘/内存环境。
2. 浏览磁盘支持的库存、Top-N、生命周期和扫描警告。
3. 选择内置 power/pipeline/aeroway profile，或按分页 key/value 生成简单规则；高级嵌套规则可在 JSON 编辑窗口中由核心 validator 验证。
4. 检查有界地图预览与 category × geometry_group 分层质量报告。
5. 选择类别、profile 属性子集和输出格式后导出。十个最小追溯字段不可取消。

快速操作见 `QUICK_START_CN.md`。命令行使用 `osm-sci --help`，GUI 使用 `osm-sci-gui` 或 Windows 独立 EXE。

## 追溯与复现

工程文件 `project.osmproject.json` 原子保存输入/profile 哈希、规则、跨页选择、导出设置、质量设置和运行结果。核心同时生成分类摘要、`classification.sqlite`、导出 audit、字段映射、Shapefile loss report 和最小化反馈包。复现比较应使用相同输入、v0.4.1、profile SHA-256 和 selection/config。

## 许可证与 OSM 数据

软件代码为 MIT License。OSM 数据通常受 Open Database License 约束；请阅读 `OSM_ATTRIBUTION_AND_ODBL.md` 并在使用或传播衍生数据库时保留适当归属。第三方运行库见 `THIRD_PARTY_NOTICES.md`。
