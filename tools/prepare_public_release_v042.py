from __future__ import annotations
import copy, json, hashlib, io, os, re, shutil, sys, time, zipfile
from pathlib import Path
EXPECTED_ORIGINAL_SHA256 = "afdad659f9a4e5410e6648083a72b46c56492efb00bc507f72a940ef15a795b8"

def sha(p:Path):
 d=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''): d.update(block)
 return d.hexdigest()

BIN_README_EN = '''# OSM Scientific Converter v0.4.2 — Windows x64 portable edition

This ZIP contains a **standalone Windows folder distribution**, not a source checkout or an installer. No separate Python, Conda or GDAL installation should be required to launch the packaged executable on a compatible Windows system. A clean-machine compatibility test has **not** yet been completed.

## Get started

1. Extract **the entire ZIP** to a new writable folder (for example, `C:\\OSMScientificConverter\\`). Do not run the EXE while it is still inside the compressed archive.
2. Keep `OSMScientificConverter_v0.4.2.exe` and the adjacent `_internal/` directory together. Double-click the EXE.
3. **Full project:** in Step 1 select `examples/sample_infrastructure.osm` and a new project folder; scan, choose a theme/profile, classify, inspect preview and export.
4. **Quick roads (no scan):** select the Step 1 quick-road action and `examples/round2_roads_small.osm`, choose a **new** output `.gpkg` path and the bundled reviewed rules. The GUI shows a bounded preview (up to the first 400 exported features), not an exhaustive spatial audit.
5. See `QUICK_START_EN.md` and `QUICK_START_CN.md` for a compact walkthrough.

## Scope and reproducibility

The quick-road option selects 13 reviewed `highway` values from the exact GDAL `lines` source layer and groups them into four classes. It is **not** a complete road network, full OSM tag inventory, or complete quality check. GDAL may still parse non-matching OSM data when reconstructing geometries. See `validation/` and `BUILD_INFO.json` for local build-host **synthetic smoke-test results**, which do not establish compatibility on a clean Windows computer.

## Distribution contents

- `OSMScientificConverter_v0.4.2.exe` and `_internal/`: portable application plus bundled dependencies.
- `examples/`: synthetic input files and reviewed rules.
- `validation/`: locally executed frozen smoke-test summaries, with machine-specific paths redacted for public distribution.
- `BUILD_INFO.json`, `CITATION.cff`, `LICENSE`, `THIRD_PARTY_NOTICES.md` and `OSM_ATTRIBUTION_AND_ODBL.md`.

**For developers:** project `src/`, `tests/`, `pyproject.toml` and Windows build scripts are supplied in the **separate source-release ZIP** and GitHub repository. They are intentionally **not** inside this portable Windows ZIP. Do not run `pip install -e`, `pytest` or `tools/build_windows_v042.bat` inside this distribution.

Software source is MIT-licensed; bundled Qt/PySide6, GDAL and other components retain their own license terms. Observe the licenses and OpenStreetMap attribution/ODbL obligations described in the accompanying notices.
'''
BIN_README_CN='''# OSM Scientific Converter v0.4.2 — Windows x64 独立版

**这是可解压使用的 Windows 独立程序包，不是源代码工程，也不是安装程序。** 在兼容的 Windows 电脑上，通常无需另装 Python、Conda 或 GDAL。尚未完成无开发环境电脑的独立兼容性实测。

## 运行方法

1. 将整个 ZIP 解压到新的可写目录，例如 `C:\\OSMScientificConverter\\`，不要在压缩文件内部双击 EXE。
2. 保持 `OSMScientificConverter_v0.4.2.exe` 和旁边的 `_internal` 文件夹相对位置不变，双击 EXE。
3. **完整项目流程**：Step 1 选择 `examples/sample_infrastructure.osm`，新建项目目录，扫描后选择分类规则、查看预览及导出。
4. **道路快速提取**：Step 1 点击 `Quick roads (no scan)`，选择 `examples/round2_roads_small.osm` 与全新的 `.gpkg` 输出路径，使用随程序提供的审核规则。Step 4 的地图最多展示前400条输出对象，仅为界面预览；Step 5 提供结果及有限审计说明。

## 重要限制

快速模式严格限于 GDAL `lines` 图层中13种被选定的 `highway` 值，归并为4类；结果不是完整道路网。快速模式不进行完整标签库存扫描和全面质量审计；GDAL 在构建几何时仍可能读取非目标数据。

`validation/` 中提供的是**构建电脑上用合成样例完成的冻结程序自检记录**。出于隐私原因，公开版本将本地绝对路径替换成了相对路径或遮蔽字段，其他自检结果和统计保持不变。`BUILD_INFO.json` 记录构建范围。该验证不等同于在没有开发环境的独立 Windows 电脑上通过兼容性测试。

## 目录与软件开发

Windows 包包含 EXE、`_internal/`、`examples/`、`validation/`、文档及许可证。**不包含**源码开发所需的 `src/`、`tests/`、`pyproject.toml` 或 `tools/build_windows_v042.bat`。如需修改源码、运行 pytest 或重新打包，请下载**独立的源码 ZIP**，不要在此 Windows 程序目录内执行构建命令。

源码采用 MIT 许可证；随附第三方运行库保留各自许可证。使用 OSM 来源数据及地图时应遵守相应署名与 ODbL 要求。
'''
QUICK_EN='''# OSM Scientific Converter v0.4.2 — Windows quick start

Extract the complete ZIP to a fresh folder. Keep the EXE and `_internal/` together. Double-click `OSMScientificConverter_v0.4.2.exe` (do not run from within the ZIP).

- **Full project:** Step 1 → `examples/sample_infrastructure.osm` → create a project → scan → classify using the power theme → bounded preview → export.
- **Quick roads:** Step 1 → `Quick roads (no scan)` → `examples/round2_roads_small.osm` → bundled reviewed highway rule → a new output GeoPackage path → run. Inspect a limited map preview in Step 4 and results/audit in Step 5.

Quick mode selects only the reviewed 13 `highway` values from exact OSM `lines` features. It is not a full road inventory or quality audit. GUI preview displays only the first 400 exported objects. To build from source or run Python tests, use the separate source package, **not** this Windows ZIP.
'''
QUICK_CN='''# OSM Scientific Converter v0.4.2 — Windows 独立版快速上手

完整解压 ZIP 后，保留 EXE 与 `_internal/` 原有相对位置，在文件夹中双击 `OSMScientificConverter_v0.4.2.exe`。

- **完整流程：** Step 1 选择 `examples/sample_infrastructure.osm`，新建项目、扫描、选择 power 规则并分类，查看预览后导出。
- **道路快速提取：** Step 1 → `Quick roads (no scan)` → `examples/round2_roads_small.osm` → 内置道路规则 → 新建 `.gpkg` 输出位置 → 运行；Step 4 浏览有限地图样本，Step 5 查看结果和审计信息。

快速模式只处理 GDAL `lines` 图层中预设13种 `highway` 值，不能视为完整道路网络、全面标签库存或完整质量审计。GUI 最多显示前400条导出对象。构建代码、运行 pytest 和重新打包的操作请使用另外提供的**源码 ZIP**，不要在此独立 Windows 程序包中执行。
'''
RELEASE_NOTES='''# OSM Scientific Converter v0.4.2 — release notes

## Changes from v0.4.1

- Exact GDAL OSM source-layer restriction for thematic classification, including strict `lines`-only selection.
- Optional `Quick roads (no scan)` workflow in GUI and CLI: 13 reviewed `highway` values, four classes, GeoPackage export, input/profile hashes and scoped audit.
- Improved interactive line selection, label display, truthful progress, and clearer quick-mode result summaries.
- Windows-compatible GDAL/OGR GeoPackage enrichment and frozen EXE headless quick-extraction subprocess.
- Deferred-RTree experiment remains off by default; three pairs did not show a reliable speed benefit.

## Release validation — scope matters

- **Windows build host (not a clean external PC):** 133 source automated tests passed, according to the build log; frozen GUI startup, two-object scan/classify/export, and four-object quick-extraction smoke tests reported success. Synthetic smoke results are included under `validation/`, with build-host absolute paths normalized/redacted for public distribution.
- **Independent ZIP inspection:** archive integrity, executable and bundled resources, citation authors and smoke evidence were checked. This is **not** independent execution of the Windows EXE.
- **Previous v0.4.2.dev1 Brazil benchmark:** fixed PBF size 856,168,766 bytes, SHA-256 `e850eeafc2ec1d94d5b6014b89b923f239a95415e663301cbe21907fa805dfc8`. Both minimal direct-GDAL and reviewed quick extraction matched the canonical OSM ID multiset for 2,067,117 lines. Single observed execution times were 89.179 s and 126.289 s, respectively, for **different workloads**. This benchmark was not rerun against the frozen v0.4.2 release and does not show speed superiority.

## Limits

Quick mode does not create a full OSM tag inventory or full pre-export geometry/quality audit. The selected highway whitelist is not a complete road-network inventory. The GUI map previews the first 400 exported objects only. A clean-Windows-host test, digital code signing, security audit and formal third-party license compliance review have **not** been completed.

## Distribution and source

The **Windows x64 ZIP** contains the frozen EXE, its `_internal` dependencies, sample inputs, documentation and build-host smoke evidence. The **source ZIP** contains `src/`, `tests/`, build tools and developer documents; the **wheel** is an installable Python distribution requiring separately configured GDAL dependencies. All are labelled v0.4.2, and the `CITATION.cff` lists Qingsong Du, Guoyu Li, Fei Wang, Wei Ma and Yanhu Mu.

The Windows *public-release ZIP* may have metadata-only modifications to the readmes, release notes and path-redacted smoke JSON compared with the original build-host ZIP. No EXE or `_internal/` payload bytes are changed; consult `PUBLIC_VALIDATION_NOTE.md` and the external SHA-256 manifest. This change requires a **new archive SHA-256**.
'''
PUBLIC_NOTE='''# Public Windows package: evidence provenance and privacy

The original Windows ZIP generated by `tools/build_windows_v042.bat` is preserved by the maintainer. This GitHub-facing ZIP is a **documentation/privacy repack** of that verified build, not a fresh Windows compilation and not a second functional test.

Changed ZIP members: `README.md`, `README_EN.md`, `README_CN.md`, `QUICK_START_EN.md`, `QUICK_START_CN.md`, `RELEASE_NOTES_v0.4.2.md`, plus `validation/GUI_SMOKE_v042.json` and `validation/FULL_WORKFLOW_SMOKE_v042.json` (absolute machine paths normalized/redacted). This `PUBLIC_VALIDATION_NOTE.md` is new. All binary runtime files (`OSMScientificConverter_v0.4.2.exe`, `_internal/`), bundled examples, citation, licenses, `BUILD_INFO.json`, and scientific hashes/counts in smoke data are preserved byte-for-byte.

Redacted fields: build-host GDAL data, CLI tools, frozen executable paths (replaced by release-relative paths), and Windows user temporary directory. `environment.public_path_redaction` flags these normalized summaries. The user-visible JSON records remain **build-host test reports**, not clean-machine validations. Original raw reports remain in the unmodified build ZIP.

The public ZIP's SHA-256 necessarily differs from the original build ZIP. Verify the **public** file against the accompanying `SHA256_PUBLIC_RELEASE.txt` and do not reuse the hash of the original build-host ZIP.
'''


def scrub_raw(raw: bytes):
 d=json.loads(raw.decode('utf-8-sig'))
 e=d['environment']
 e['gdal']['data_path']='_internal/Library/share/gdal'
 e['gdal']['ogr2ogr']='_internal/ogr2ogr.exe'
 e['gdal']['ogrinfo']='_internal/ogrinfo.exe'
 e['python']['executable']='OSMScientificConverter_v0.4.2.exe'
 e['temporary_directory']='[redacted: build-host temporary directory]'
 e['public_path_redaction']='Absolute build-host paths replaced for public release; original raw report preserved by maintainer.'
 d['public_release_note']='Only environment paths were normalized; test status, counts, hashes, and timings were not changed.'
 return (json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8')

replacements = {
 'README.md': BIN_README_EN.encode(),
 'README_EN.md': BIN_README_EN.encode(),
 'README_CN.md': BIN_README_CN.encode(),
 'QUICK_START_EN.md': QUICK_EN.encode(),
 'QUICK_START_CN.md': QUICK_CN.encode(),
 'RELEASE_NOTES_v0.4.2.md': RELEASE_NOTES.encode(),
 'validation/GUI_SMOKE_v042.json': None,
 'validation/FULL_WORKFLOW_SMOKE_v042.json': None,
}

def new_info(name, dt=None):
 z=zipfile.ZipInfo(name, date_time=dt or (2026,10,11,20,30,0))
 z.compress_type=zipfile.ZIP_DEFLATED
 z.external_attr=(0o644<<16)
 z.create_system=3
 return z



def arcname(name: str) -> str:
    """ZIP member names are POSIX paths even when input ZIP used Windows separators."""
    return name.replace("\\", "/")

def publicize(input_zip: Path, out_dir: Path, skip_hash: bool=False):
    input_zip = input_zip.resolve()
    out_dir = out_dir.resolve()
    if not input_zip.is_file(): raise FileNotFoundError(input_zip)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_zip = out_dir / 'OSMScientificConverter_v0.4.2_Windows_x64.zip'
    if input_zip == output_zip: raise ValueError('Input and output ZIP must be different files.')
    if output_zip.exists(): raise FileExistsError(f'Refusing to overwrite: {output_zip}')
    original_hash=sha(input_zip)
    if not skip_hash and original_hash!=EXPECTED_ORIGINAL_SHA256:
        raise RuntimeError(f'Original ZIP SHA-256 mismatch: {original_hash}; expected {EXPECTED_ORIGINAL_SHA256}. Do not run on another binary version.')
    print('Original build ZIP verified:',original_hash,flush=True)
    tmp=output_zip.with_suffix('.building')
    try:
        with zipfile.ZipFile(input_zip, 'r') as zin, zipfile.ZipFile(
            tmp, 'w', allowZip64=True, compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zout:
            source_infos = zin.infolist()
            source_paths = [arcname(info.filename) for info in source_infos]
            if len(set(source_paths)) != len(source_paths):
                raise ValueError('Original ZIP has duplicate member names after path normalization.')
            for i, info in enumerate(source_infos, 1):
                name = arcname(info.filename)
                output_info = copy.copy(info)
                output_info.filename = name  # Always use portable ZIP forward slashes.
                if name in replacements:
                    data = replacements[name]
                    if data is None:
                        data = scrub_raw(zin.read(info))
                    zout.writestr(
                        output_info, data,
                        compress_type=info.compress_type, compresslevel=6
                    )
                else:
                    with zin.open(info, 'r') as fi, zout.open(
                        output_info, 'w', force_zip64=(info.file_size > (1 << 30))
                    ) as fo:
                        shutil.copyfileobj(fi, fo, length=1 << 20)
                if i % 500 == 0:
                    print('Repacked', i, 'of', len(source_infos), flush=True)
            zout.writestr(new_info('PUBLIC_VALIDATION_NOTE.md'), PUBLIC_NOTE)

        with zipfile.ZipFile(tmp, 'r') as public, zipfile.ZipFile(input_zip, 'r') as original:
            bad = public.testzip()
            if bad is not None:
                raise ValueError('Public ZIP failed CRC on ' + bad)
            old_infos = original.infolist()
            new_infos = public.infolist()
            old_members = {arcname(info.filename): info for info in old_infos}
            new_members = {arcname(info.filename): info for info in new_infos}
            if len(old_members) != len(old_infos) or len(new_members) != len(new_infos):
                raise AssertionError('Duplicate member names after normalizing separators')
            if set(new_members) != set(old_members) | {'PUBLIC_VALIDATION_NOTE.md'}:
                raise AssertionError('Public ZIP member list differs unexpectedly')
            for name, old_info in old_members.items():
                if name in replacements:
                    continue
                new_info_obj = new_members[name]
                if (new_info_obj.file_size != old_info.file_size
                        or new_info_obj.CRC != old_info.CRC):
                    raise AssertionError('Unexpected modified archive member ' + name)
            for name in [
                'OSMScientificConverter_v0.4.2.exe',
                'CITATION.cff', 'LICENSE', 'BUILD_INFO.json'
            ]:
                if public.read(new_members[name]) != original.read(old_members[name]):
                    raise AssertionError('Core member changed: ' + name)
            for name in [
                'validation/GUI_SMOKE_v042.json',
                'validation/FULL_WORKFLOW_SMOKE_v042.json'
            ]:
                data = public.read(new_members[name])
                if b'D:\\OSM' in data or b'dqs' in data:
                    raise AssertionError('Build-host private path survived in ' + name)
                if b'public_path_redaction' not in data:
                    raise AssertionError('Missing redaction marker in ' + name)
            if any('\\' in info.filename for info in new_infos):
                raise AssertionError('Public ZIP still contains Windows-style member separators')
        tmp.replace(output_zip)
        new_hash=sha(output_zip)
        manifest=out_dir/'SHA256_PUBLIC_RELEASE.txt'
        manifest.write_text(f'{new_hash}  {output_zip.name}\n',encoding='utf-8')
        report={
            'software_version':'0.4.2',
            'original_build_zip_sha256':original_hash,
            'public_release_zip_sha256':new_hash,
            'file_name':output_zip.name,
            'size_bytes':output_zip.stat().st_size,
            'method':'Metadata/privacy repack: no EXE, _internal, example or citation changes',
            'original_build_host_tests':'133 passed; GUI/full/quick frozen smoke PASS (provided build log)',
            'public_release_integrity':'ZIP CRC PASS; all original unaffected members unchanged (CRC and size); critical EXE and manifest bytes compared',
            'not_tested':'No second Windows execution was performed by metadata repack; clean-host compatibility not established',
        }
        (out_dir/'PUBLIC_RELEASE_VERIFICATION.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        release_notes = f"""# OSM Scientific Converter v0.4.2

Windows x64 portable release and matching Python/source artifacts. Software citation: Qingsong Du, Guoyu Li, Fei Wang, Wei Ma, Yanhu Mu.

## What changed

- Exact OSM source-layer filtering and reviewed 13-value, four-category highway extraction from `lines`.
- GUI quick-road workflow with bounded map preview, click-to-inspect features and limited audit summary.
- Improved Windows GeoPackage generation and frozen EXE quick-extraction support.

## Scope of the tests

On the Windows build computer, 133 automated tests and frozen GUI/full-workflow/four-road quick-extract smoke tests passed. The public ZIP preserves the executable and bundled libraries byte-for-byte but redacts absolute file paths in two publicly bundled validation JSON records. This release has **not** been independently tested on a clean Windows host.

The older Brazil Sudeste experiment is pre-release development benchmark evidence (2,067,117 matching highway identifiers); it is not a benchmark rerun of the final frozen EXE. Direct GDAL and converter quick mode perform different workloads and must not be compared as equivalent.

## Download and installation

Download `OSMScientificConverter_v0.4.2_Windows_x64.zip`, extract all files, keep `_internal/` next to the EXE, and launch `OSMScientificConverter_v0.4.2.exe`. The source ZIP and Python wheel are separate release assets. Quick mode is not a full road inventory or full pre-export quality audit. OSM/ODbL attribution and bundled third-party licenses apply.

## SHA-256 of the PUBLIC Windows ZIP

`{new_hash}`

This value is for the public ZIP (documentation/privacy repack), **not** the earlier original build ZIP.
"""
        (out_dir/'GITHUB_RELEASE_NOTES.md').write_text(release_notes,encoding='utf-8')
        print('PUBLIC WINDOWS ZIP SUCCESS:',output_zip,flush=True)
        print('SHA256:',new_hash,flush=True)
        print('Upload ONLY this new ZIP to GitHub after manual GUI acceptance.',flush=True)
    except Exception:
        if tmp.exists(): tmp.unlink()
        raise

if __name__ == '__main__':
    import argparse
    ap=argparse.ArgumentParser(description='Documentation and path-redaction repack of VERIFIED OSM Scientific Converter v0.4.2 Windows ZIP; does not modify EXE.')
    ap.add_argument('--input',dest='input_zip',required=True,help='Path to original Windows build ZIP')
    ap.add_argument('--out-dir',required=True,help='Output directory for public ZIP, checksum and verification report')
    ns=ap.parse_args()
    publicize(Path(ns.input_zip),Path(ns.out_dir))
