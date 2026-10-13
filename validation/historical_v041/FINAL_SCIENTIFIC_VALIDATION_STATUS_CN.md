# 最终科学验证状态

本文件严格区分“v0.4.1 软件硬化验收完成”与“论文投稿所需科学证据尚未全部完成”。自动测试、规则一致性、本地参考集或本地发行物均不被表述为物理世界真值或完整投稿证据。

## v0.4.1 软件硬化结论

- 五项指定功能修复已经实现：真实字段子集导出并强制保留 10 个追溯字段；确定性类别×几何分层抽样；类别适用的 required/recommended/optional 字段；简单规则构建器与高级 JSON 校验编辑器；跨页、搜索、分页与工程文件的选择状态持久化。
- Python 3.12.13 与 3.13.14 下，源码及安装后的最终 wheel 共四次严格测试，均为 90/90 通过，并启用 warnings-as-errors。最终 wheel SHA-256 为 `b882fb9988a7e9adec3c561f7e28563d16f54a11b28dfe806eacfc4597f63ec3`。
- Windows 独立 EXE SHA-256 为 `0c5911f3ffa8fa4e12da0dccde51950250a1b3b9b4e60f1ae94ab24d3c678e25`。在清除开发环境 PATH/PYTHONPATH/PYTHONHOME/Conda/GDAL 变量后，冻结 EXE 使用稳定 GDAL 3.13.2 完成扫描、分类、字段子集导出和分层质量检查。
- 真实 packaged-EXE GUI 验收覆盖 Berlin power、South Korea aeroway、New York pipeline；三例均为真实 GUI 控件的程序化操作并保存每例 4 张窗口截图，不表述为人工鼠标会话。GUI 类别集合与导出审计中的非空 `resolved_categories` 一致。
- 总验证 `PHASE3_V041_VALIDATION.json` 为 14/14 检查通过。冻结 Phase 2 v0.3.1 证据及 v0.4.0 release JSON 哈希不变；分类器、规则引擎、扫描器及 profile 分类表达式未被改写。
- 正式本地候选制品仅允许 7 项：wheel、sdist、干净源码 ZIP、Windows ZIP、验证证据 ZIP、`RELEASE_V041.json`、`SHA256SUMS.txt`。最终文件身份以这两个清单文件为准。

## 四地区性能与复现

Berlin、South Korea、New York、Quebec 均完成全新 v0.4.1 + GDAL 3.13.2 分阶段运行和第二次分类/导出复现。四例的输入/profile 哈希、分类计数、OSM ID 集、导出要素/图层计数一致，SQLite 与 GPKG 完整性均为 `ok`。详细时间、峰值内存、磁盘和输出大小见 `FINAL_RELEASE_PERFORMANCE_AND_REPRODUCIBILITY.json` 与 `RESULTS_EVIDENCE_V041.md`。数据库字节级一致性未被不合理地强制要求。

## 分类参考集

- power、aeroway、pipeline 每专题均确定性抽取 50 个正例与 30 个负例，覆盖 Berlin、South Korea、New York、Quebec，且均通过点/线/面/关系、活动/生命周期和多地区覆盖检查。
- 当前 OSM 标签语义暂定 F1：power `0.948454`、aeroway `0.932039`、pipeline `0.803419`。pipeline 暂定混淆矩阵包含 20 个假阳性，已保留用于错误类型审查，不作隐藏或美化。
- 标签由 agent 依照预先声明的 OSM 标签语义判定；`independent_author_domain_review=false`，且 `publication_use_permitted_before_independent_review=false`。因此这些数值不是独立验证后的最终精度，也不代表物理设施真值。

## 工具对照

同一 Berlin PBF 快照下，已执行 OSM Scientific Converter v0.4.1 与 GDAL 默认 `osmconf` 的局部双工具对照：6,726/6,726 目标 OSM ID 可回查，41,179/42,376 原始键值赋值精确保留，3/3 关系可回查，272/272 生命周期对象的生命周期标签仍可检测。QGIS/QuickOSM 未安装；未提供产品、版本、日期和范围一致的预制 Shapefile。因此两项均保持 `not_executed`，不得模拟，该结果不得称为完整四方比较。

## 投稿决定

本地 v0.4.1 软件候选可以冻结和哈希，但 SoftwareX 稿件仍为“不可投稿”。提交前必须完成：独立参考集复核；同快照同范围的 QuickOSM 与指定预制 Shapefile 比较；真实作者、单位、通讯作者及利益声明；公共 GitHub 仓库与 v0.4.1 release；Zenodo DOI；软件/数据可用性 URL；最终投稿图表与相应声明。任何缺失值均不得推测或虚构。
