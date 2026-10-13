# v0.4.2 Windows 发布前验收清单

在 Conda/GDAL/PySide6 Windows 环境中，按照以下顺序执行。**任何失败均应停止正式公开 Windows ZIP**：

1. `python -m pip install -e .[test,package]`；`osm-sci --version` 应为 `0.4.2`。
2. `python -m pytest -q`：记录完整数字、GDAL/Python/PySide6 版本与 skip 统计；包含 GUI click/Preview、实际 GPKG 和冻结子进程相关测试。
3. `tools\build_windows_v042.bat`：调用 PowerShell 编译 PyInstaller onedir，验证 GUI `--smoke-test` 返回状态、版本、frozen 标志，运行冻结的 `--headless-cli quick-extract` 四道路样例，检查4条、lines、audit SHA 与 GPKG 完整性，然后生成 Windows ZIP 与 SHA-256。
4. 用另一台无开发环境的 Windows x64（如可用）完整解压 ZIP，启动 GUI、执行 `Quick roads (no scan)`、Step 4 点选道路与 Step 5 结果摘要，再试完整项目扫描/分类/导出。记录实际操作截图。
5. `Get-FileHash` 检查 SHA-256，检查 OSM/ODbL attribution 与 PySide6/GDAL/PROJ 第三方许可证。
6. 核对 GitHub 标签、Release 文件、CITATION 的作者与 DOI/发布日期、论文 Data/Code Availability 和最终图片实际版本后再对外发布。

目前**不能声称** Windows EXE 已在本对话的 Linux 构建环境验证，也不能把历史 v0.4.1 文件当作本版证据。
