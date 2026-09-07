# OSM Scientific Converter v0.4.1

OSM Scientific Converter 是用于科研专题数据准备的可审计 OpenStreetMap（OSM）桌面与命令行工作流。软件针对一个确定日期的本地 `.osm` 或 `.osm.pbf` 快照，盘点输入中实际存在的 tag 词汇，保留 GDAL OSM driver 暴露的五个逻辑图层，应用版本化 JSON profile，保存对象/规则追溯信息，执行确定性的过程检查，并将结果导出为 GeoPackage、GeoJSON 或 Shapefile，同时记录格式转换产生的实际信息损失。

经验证的软件版本仍为 **v0.4.1**。本轮同行评议后的 GitHub 更新只修改科研说明文档和论文图件；不会修改已发布的 scanner、classifier、rule evaluator、内置 profiles、exporter、数据库 schema、测试或二进制发行物。

## 科学范围

软件解决的是**可复现的专题数据准备**，并不把 OSM filtering 本身作为新方法，也不以内部过程检查代替外部真实精度验证。对于固定的本地快照，工作流保存三类相互关联的 provenance：

- **数据 provenance：**输入 SHA-256、OSM 对象/源图层表示及运行环境；
- **语义 provenance：**实际观察到的 tag inventory、解析后的 profile/rules、生命周期处理、candidate/confirmed 区分和 profile SHA-256；
- **计算与导出 provenance：**软件版本、工程配置、确定性检查、输出 schema、字段映射和实际格式损失。

结果只描述给定 OSM 快照和所采用的语义规则，并不保证现实基础设施完整性、位置精度或 OSM 的普遍专题正确性。

## 五步 GUI 工作流

1. 选择输入和工程目录，记录输入 SHA-256 以及 GDAL/内存/磁盘环境；
2. 通过磁盘支持的 inventory 和 lazy query 浏览图层、tag、生命周期及警告；
3. 使用 `power`、`pipeline`、`aeroway` 内置 profile，从实际 key/value 中选择，或验证自定义 JSON profile；
4. 查看有界空间预览并运行确定性的 category × geometry 过程检查；
5. 选择类别/属性，导出 GeoPackage、GeoJSON 或 Shapefile，同时保留 mandatory provenance 和格式损失报告。

CLI 使用 `osm-sci --help`，GUI 使用 `osm-sci-gui`。论文中的英文 GUI 截图来自 v0.4.1 Windows 正式打包程序的实际 Berlin power 工作流。

## 与已有工具的关系

OSM filtering 和 conversion 已经是成熟能力。GDAL 是本软件使用的底层 OSM reconstruction engine；osm2pgsql 更适合 PostgreSQL/PostGIS 持久化数据库及大规模/planet-scale 场景；Osmosis 和 osmconvert 适合命令行文件处理；QuickOSM 支持 QGIS/Overpass；OSMnx 提供程序化 OSM 获取与分析；OSM2CDR 提供在线格式转换；ohsome 支持 OSM 历史查询和统计。

本软件更窄的定位是将**输入快照专属词汇发现、显式/版本化语义规则、对象级 provenance、确定性提取过程检查、GUI/CLI 一致性和格式损失证据**整合在一个本地科研工程中。详见 `docs/SCIENTIFIC_SCOPE_AND_RELATED_TOOLS.md`。

## Profile 构建

内置 profile 是显式语义定义示例，并非全球通用 ontology。建议先扫描目标快照，检查实际 key/value、geometry 和 lifecycle 分布，再结合 OSM 文档和领域知识编写 inclusive/exclusive/candidate 规则，复核类别数量与确定性样本，最后冻结并记录 resolved JSON 的 SHA-256。Taginfo 和 ohsome 只能作为外部背景信息，不能替代本地 inventory。详见 `docs/PROFILE_AUTHORING.md`。

## 经验证的尺度边界

v0.4.1 验证包括 Berlin（94.2 MiB）、South Korea（271.3 MiB）、New York（471.4 MiB）和 Quebec（1.08 GiB），最多重建 12.38 million features；测试工作站上的完整工作流 peak RSS 为 481.1-633.1 MiB。这些结果支持文中报告的区域级和一个已测试国家级工作流，**不能解释为 planet-scale benchmark**。详见 `docs/SCALABILITY_AND_LIMITS.md`。

## 输出格式

- **GeoPackage：**已实现且为默认输出，用作基于标准的 evidence-bearing analytical output；
- **GeoJSON：**已实现，用于透明文本交换；
- **Shapefile：**已实现，用于 legacy interoperability，并输出字段映射和实际 loss report；
- **GeoParquet：**仅作为未来分析型扩展讨论，**v0.4.1 未实现**。

详见 `docs/FORMAT_SUPPORT.md`。

## 论文图件与公开证据

修订后的 SoftwareX 稿件包含 **6 幅图**。`paper/figures/` 中保存全部输出、源数据和可复现 Python 脚本：Figure 1 架构、Figure 2 真实英文 GUI、Figure 3 四验证区域位置、Figure 4 专题分类示例、Figure 5 Berlin 导出审计与重复运行复现检查、Figure 6 运行时间和 peak RSS。Figure 3 使用 Natural Earth public-domain 底图，仅用代表点表示 Geofabrik extracts，不表示精确边界。

公开验证摘要位于 `validation/public/`。区域 PBF 原始数据和私人 project databases 不在仓库中再分发。

## 许可证与数据

代码采用 MIT License。OSM 数据需遵守适用的 OpenStreetMap/Open Database License 条款，见 `OSM_ATTRIBUTION_AND_ODBL.md`。第三方运行库和论文图件数据说明见 `THIRD_PARTY_NOTICES.md`。
