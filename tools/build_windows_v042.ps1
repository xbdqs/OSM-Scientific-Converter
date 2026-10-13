# OSM Scientific Converter v0.4.2 standalone Windows x64 build
# Run only inside an activated conda environment containing GDAL + PySide6.
param([string]$OutputRoot = 'dist_windows_v042')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$OldPlatform = $env:QT_QPA_PLATFORM
$OldPath = $env:PATH
try {
    if (-not $env:CONDA_PREFIX) { throw 'Activate your OSM conda GDAL environment first.' }
    Write-Host '[1/7] Check dependencies and run tests...'
    python -m pip install -e '.[test,package]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed' }
    $Version = (python -c 'from osm_scientific_converter import __version__; print(__version__)').Trim()
    if ($Version -ne '0.4.2') { throw "Expected v0.4.2, found $Version after editable installation." }
    $env:QT_QPA_PLATFORM = 'offscreen'
    python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed. No Windows ZIP will be created.' }
    $Ogr2Ogr = (Get-Command ogr2ogr.exe -ErrorAction Stop).Source
    $OgrInfo = (Get-Command ogrinfo.exe -ErrorAction Stop).Source
    # Read version through the already resolved GDAL CLI. Avoid native Windows
    # PowerShell/Python -c quote removal around gdal.VersionInfo("--version").
    $GdalVersionLines = @(& $OgrInfo '--version')
    if ($LASTEXITCODE -ne 0 -or $GdalVersionLines.Count -eq 0 -or -not $GdalVersionLines[0]) {
        throw 'Unable to read GDAL version from ogrinfo.exe --version'
    }
    $BundleVersion = ([string]$GdalVersionLines[0]).Trim()
    $GdalData = $null
    foreach ($v in @($env:GDAL_DATA,(Join-Path $env:CONDA_PREFIX 'Library\share\gdal'),(Join-Path $env:CONDA_PREFIX 'share\gdal'))) {
        if ($v -and (Test-Path -LiteralPath $v -PathType Container)) { $GdalData = (Resolve-Path -LiteralPath $v).Path; break }
    }
    $ProjData = $null
    foreach ($v in @($env:PROJ_DATA,$env:PROJ_LIB,(Join-Path $env:CONDA_PREFIX 'Library\share\proj'),(Join-Path $env:CONDA_PREFIX 'share\proj'))) {
        if ($v -and (Test-Path -LiteralPath (Join-Path $v 'proj.db') -PathType Leaf)) { $ProjData = (Resolve-Path -LiteralPath $v).Path; break }
    }
    if (-not $GdalData -or -not $ProjData) { throw 'GDAL_DATA or PROJ_DATA not resolved; install conda-forge gdal/proj.' }
    $Resources = Join-Path $Repo 'src\osm_scientific_converter\resources'
    foreach ($f in @('osmconf.ini','profiles\power.json','profiles\pipeline.json','profiles\aeroway.json','profiles\reviewer_roads_lines_v1.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Resources $f))) { throw "Missing resource: $f" }
    }
    $Out = Join-Path $Repo $OutputRoot
    # Fail closed rather than delete a folder accidentally specified by caller.
    if (Test-Path -LiteralPath $Out) { throw "Output directory already exists. Rename/delete after archiving: $Out" }
    New-Item -ItemType Directory -Path $Out | Out-Null
    $Dist = Join-Path $Out 'dist'
    $Build = Join-Path $Out 'build'
    $Specs = Join-Path $Out 'spec'
    $AppName = 'OSMScientificConverter_v0.4.2'
    $PyArgs = @(
        '--noconfirm','--clean','--onedir','--windowed',
        '--name',$AppName,'--distpath',$Dist,'--workpath',$Build,'--specpath',$Specs,
        '--collect-all','PySide6','--collect-all','osgeo',
        '--add-data',"$GdalData;gdal_data",'--add-data',"$ProjData;proj_data",
        '--add-data',"$Resources;osm_scientific_converter/resources",
        '--add-binary',"$Ogr2Ogr;.",'--add-binary',"$OgrInfo;."
    )
    $Plugins = Join-Path $env:CONDA_PREFIX 'Library\lib\gdalplugins'
    if (Test-Path -LiteralPath $Plugins) { $PyArgs += @('--add-data',"$Plugins;gdalplugins") }
    $PyArgs += 'tools/gui_entry_v042.py'
    Write-Host '[2/7] Build Windows onedir...'
    python -m PyInstaller @PyArgs
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $Dir = Join-Path $Dist $AppName
    $Exe = Join-Path $Dir ($AppName + '.exe')
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw 'Missing frozen EXE' }
    $Internal = Join-Path $Dir '_internal'
    foreach ($f in @('osmconf.ini','profiles\reviewer_roads_lines_v1.json')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Internal "osm_scientific_converter\resources\$f"))) { throw "Frozen resource missing: $f" }
    }
    foreach ($f in @('ogr2ogr.exe','ogrinfo.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Internal $f))) { throw "Bundled GDAL CLI missing: $f" }
    }
    $env:PATH = "$Internal;$env:PATH"
    $Smoke = Join-Path $Out 'GUI_SMOKE_v042.json'
    Write-Host '[3/7] Frozen GUI offscreen self-test...'
    $p = Start-Process -FilePath $Exe -ArgumentList @('--smoke-test','--smoke-report',"`"$Smoke`"") -Wait -PassThru
    if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Smoke)) { throw 'Frozen GUI self-test failed' }
    $Json = Get-Content -LiteralPath $Smoke -Raw | ConvertFrom-Json
    if ($Json.status -ne 'success' -or $Json.software_version -ne '0.4.2' -or -not $Json.frozen -or [int]$Json.five_step_pages -ne 5) {
        throw 'Frozen GUI self-test report mismatch'
    }
    Write-Host '[3b/7] Frozen complete-project scan/classify/export self-test...'
    $Project = Join-Path $Out 'SMOKE_FULL_PROJECT'
    $FullOutput = Join-Path $Out 'SMOKE_FULL_PROJECT.gpkg'
    $FullSmoke = Join-Path $Out 'FULL_WORKFLOW_SMOKE_v042.json'
    $Sample = Join-Path $Repo 'examples\sample_infrastructure.osm'
    $fullArgs = @('--smoke-test','--smoke-report',"`"$FullSmoke`"",'--workflow-input',"`"$Sample`"",
                  '--workflow-project',"`"$Project`"",'--workflow-output',"`"$FullOutput`"")
    $p = Start-Process -FilePath $Exe -ArgumentList $fullArgs -Wait -PassThru
    if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $FullSmoke)) { throw 'Frozen full workflow self-test failed' }
    $f = Get-Content -LiteralPath $FullSmoke -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($f.status -ne 'success' -or $f.software_version -ne '0.4.2' -or -not $f.frozen -or -not $f.workflow.export_exists) {
        throw 'Frozen full workflow report mismatch'
    }
    if (-not (Test-Path -LiteralPath $FullOutput)) { throw 'Frozen full workflow output missing' }
    Write-Host '[4/7] Frozen headless quick extraction (no Python -m subprocess)...' 
    $Source = Join-Path $Repo 'examples\round2_roads_small.osm'
    $Rules = Join-Path $Internal 'osm_scientific_converter\resources\profiles\reviewer_roads_lines_v1.json'
    $Quick = Join-Path $Out 'SMOKE_QUICK_ROADS.gpkg'
    $args = @('--headless-cli','quick-extract',"`"$Source`"",'--rules',"`"$Rules`"",'--output',"`"$Quick`"")
    $p = Start-Process -FilePath $Exe -ArgumentList $args -Wait -PassThru
    $Audit = "$Quick.audit.json"
    if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $Quick) -or -not (Test-Path -LiteralPath $Audit)) {
        throw 'Frozen quick extraction did not produce output + audit; do not release'
    }
    $QuickJson = Get-Content -LiteralPath $Audit -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($QuickJson.status -ne 'success' -or [int]$QuickJson.feature_count -ne 4 -or $QuickJson.source_layer -ne 'lines' -or $QuickJson.software_version -ne '0.4.2' -or $QuickJson.profile_id -ne 'reviewer_roads_lines_v1') {
        throw 'Frozen quick extraction audit failed'
    }
    Write-Host '[5/7] Check frozen GeoPackage rows and SQLite integrity...'
    # Keep SQL and quotes in a Python script instead of PowerShell -c:
    # the latter may strip nested quote marks on Windows PowerShell 5.1.
    python (Join-Path $Repo 'tools\verify_frozen_quick_gpkg_v042.py') "$Quick"
    if ($LASTEXITCODE -ne 0) { throw 'Frozen GPKG integrity/provenance failed' }
    Write-Host '[6/7] Include required documentation, sample inputs and build evidence...'
    foreach ($f in @('README.md','README_CN.md','README_EN.md','QUICK_START_CN.md','QUICK_START_EN.md',
                     'RELEASE_NOTES_v0.4.2.md','LICENSE','CITATION.cff','THIRD_PARTY_NOTICES.md','OSM_ATTRIBUTION_AND_ODBL.md')) {
        Copy-Item -LiteralPath (Join-Path $Repo $f) -Destination $Dir -Force
    }
    Copy-Item -LiteralPath (Join-Path $Repo 'examples') -Destination $Dir -Recurse
    # No zip-bundled experiment GeoPackages; quick demo can be regenerated.
    $Evidence = Join-Path $Dir 'validation'
    New-Item -ItemType Directory -Path $Evidence | Out-Null
    Copy-Item -LiteralPath $Smoke -Destination $Evidence
    Copy-Item -LiteralPath $FullSmoke -Destination $Evidence
    Copy-Item -LiteralPath $Audit -Destination $Evidence
    $Info = [ordered]@{
        status='built_and_locally_smoke_tested'; software_version='0.4.2';
        gdal_version=$BundleVersion; conda_environment=$env:CONDA_DEFAULT_ENV;
        built_at_utc=(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ');
        frozen_gui_test='validation/GUI_SMOKE_v042.json';
        frozen_full_workflow_test='validation/FULL_WORKFLOW_SMOKE_v042.json';
        frozen_quick_test='validation/SMOKE_QUICK_ROADS.gpkg.audit.json';
        note='Smoke test is performed on the build machine, not an independent clean Windows host.'
    }
    $Info | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $Dir 'BUILD_INFO.json') -Encoding UTF8
    Write-Host '[7/7] ZIP and hash successful build...'
    $WinZip = Join-Path $Out ($AppName + '_Windows_x64.zip')
    Compress-Archive -Path (Join-Path $Dir '*') -DestinationPath $WinZip -CompressionLevel Optimal
    if (-not (Test-Path -LiteralPath $WinZip)) { throw 'Windows ZIP missing' }
    $Hash = (Get-FileHash -LiteralPath $WinZip -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  $(Split-Path -Leaf $WinZip)" | Set-Content -LiteralPath (Join-Path $Out 'SHA256_WINDOWS.txt') -Encoding ascii
    Write-Host "SUCCESS: $WinZip" -ForegroundColor Green
    Write-Host "SHA256: $Hash"
}
finally {
    $env:QT_QPA_PLATFORM = $OldPlatform
    $env:PATH = $OldPath
}
