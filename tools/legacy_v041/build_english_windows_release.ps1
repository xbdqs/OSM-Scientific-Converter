param(
    [string]$OutputRoot = "dist_english_v041"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

function Resolve-ExistingDirectory {
    param(
        [string[]]$Candidates,
        [string]$RequiredFile,
        [string]$Description
    )

    foreach ($Candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) {
            continue
        }

        $Expanded = [Environment]::ExpandEnvironmentVariables($Candidate)
        if (-not (Test-Path -LiteralPath $Expanded -PathType Container)) {
            continue
        }

        if ([string]::IsNullOrWhiteSpace($RequiredFile) -or
            (Test-Path -LiteralPath (Join-Path $Expanded $RequiredFile) -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $Expanded).Path
        }
    }

    throw "$Description could not be resolved. Checked: $($Candidates -join '; ')"
}

Write-Host "[1/9] Installing the current English source tree..."
python -m pip install -e ".[test,package]"
if ($LASTEXITCODE -ne 0) {
    throw "Editable installation failed."
}

Write-Host "[2/9] Running the strict source test suite..."
$PreviousQtPlatform = $env:QT_QPA_PLATFORM
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -W error
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed. The Windows package was not built."
}

Write-Host "[3/9] Resolving GDAL command-line tools..."
$Ogr2Ogr = (Get-Command ogr2ogr.exe -ErrorAction Stop).Source
$OgrInfo = (Get-Command ogrinfo.exe -ErrorAction Stop).Source

if ([string]::IsNullOrWhiteSpace($env:CONDA_PREFIX)) {
    throw "CONDA_PREFIX is not set. Activate osm-scientific-converter-phase3 first."
}

Write-Host "[4/9] Resolving GDAL, PROJ and application resource directories..."
$GdalDataFromPython = (
    python -c "from osgeo import gdal; print(gdal.GetConfigOption('GDAL_DATA') or '')"
).Trim()

$ProjDataFromGdal = (
    python -c "from osgeo import osr; p=osr.GetPROJSearchPaths(); print(p[0] if p else '')"
).Trim()

$GdalData = Resolve-ExistingDirectory `
    -Candidates @(
        $env:GDAL_DATA,
        $GdalDataFromPython,
        (Join-Path $env:CONDA_PREFIX "Library\share\gdal"),
        (Join-Path $env:CONDA_PREFIX "share\gdal")
    ) `
    -RequiredFile "" `
    -Description "GDAL data directory"

$ProjData = Resolve-ExistingDirectory `
    -Candidates @(
        $env:PROJ_DATA,
        $env:PROJ_LIB,
        $ProjDataFromGdal,
        (Join-Path $env:CONDA_PREFIX "Library\share\proj"),
        (Join-Path $env:CONDA_PREFIX "share\proj")
    ) `
    -RequiredFile "proj.db" `
    -Description "PROJ data directory"

$PackageResources = Join-Path $Repo "src\osm_scientific_converter\resources"
if (-not (Test-Path -LiteralPath $PackageResources -PathType Container)) {
    throw "Application resources directory is missing: $PackageResources"
}

$RequiredResources = @(
    "osmconf.ini",
    "profiles\aeroway.json",
    "profiles\pipeline.json",
    "profiles\power.json"
)
foreach ($RelativeResource in $RequiredResources) {
    $ResourceFile = Join-Path $PackageResources $RelativeResource
    if (-not (Test-Path -LiteralPath $ResourceFile -PathType Leaf)) {
        throw "Required application resource is missing: $ResourceFile"
    }
}

Write-Host "  ogr2ogr: $Ogr2Ogr"
Write-Host "  ogrinfo: $OgrInfo"
Write-Host "  GDAL data: $GdalData"
Write-Host "  PROJ data: $ProjData"
Write-Host "  Application resources: $PackageResources"

$OutputBase = Join-Path $Repo $OutputRoot
$DistRoot = Join-Path $OutputBase "dist"
$WorkRoot = Join-Path $OutputBase "build"
$SpecRoot = Join-Path $OutputBase "spec"
$AppName = "OSMScientificConverter_v0.4.1"
$Built = Join-Path $DistRoot $AppName
$ZipPath = Join-Path $OutputBase "OSMScientificConverter_v0.4.1_Windows_x64_English.zip"
$SmokeReport = Join-Path $OutputBase "WINDOWS_ENGLISH_STARTUP_SMOKE.json"

if (Test-Path -LiteralPath $OutputBase) {
    Remove-Item -LiteralPath $OutputBase -Recurse -Force
}
New-Item -ItemType Directory -Path $DistRoot, $WorkRoot, $SpecRoot -Force | Out-Null

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", $AppName,
    "--distpath", $DistRoot,
    "--workpath", $WorkRoot,
    "--specpath", $SpecRoot,
    "--collect-all", "PySide6",
    "--collect-all", "osgeo",
    "--add-data", "$GdalData;gdal_data",
    "--add-data", "$ProjData;proj_data",
    "--add-data", "$PackageResources;osm_scientific_converter/resources",
    "--add-binary", "$Ogr2Ogr;.",
    "--add-binary", "$OgrInfo;."
)

$GdalPlugins = Join-Path $env:CONDA_PREFIX "Library\lib\gdalplugins"
if (Test-Path -LiteralPath $GdalPlugins -PathType Container) {
    $PyInstallerArgs += @("--add-data", "$GdalPlugins;gdalplugins")
}

$PyInstallerArgs += "tools/gui_entry_v041.py"

Write-Host "[5/9] Building the standalone English Windows application..."
python -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

if (-not (Test-Path -LiteralPath $Built -PathType Container)) {
    throw "PyInstaller returned successfully, but the expected output directory was not created: $Built"
}

$Exe = Join-Path $Built "$AppName.exe"
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
    throw "The expected executable was not created: $Exe"
}

$BundledResources = Join-Path $Built "_internal\osm_scientific_converter\resources"
foreach ($RelativeResource in $RequiredResources) {
    $BundledFile = Join-Path $BundledResources $RelativeResource
    if (-not (Test-Path -LiteralPath $BundledFile -PathType Leaf)) {
        throw "PyInstaller omitted a required bundled resource: $BundledFile"
    }
}

Write-Host "[6/9] Running a smoke test against the packaged executable..."
$PreviousPythonPath = $env:PYTHONPATH
$PreviousCleanFlag = $env:OSM_SCI_CLEAN_ENV
try {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    $env:OSM_SCI_CLEAN_ENV = "1"
    $env:QT_QPA_PLATFORM = "offscreen"

    $SmokeArguments = "--smoke-test --smoke-report `"$SmokeReport`""
    $SmokeProcess = Start-Process `
        -FilePath $Exe `
        -ArgumentList $SmokeArguments `
        -PassThru `
        -Wait

    if ($SmokeProcess.ExitCode -ne 0) {
        throw "The packaged executable smoke test exited with code $($SmokeProcess.ExitCode)."
    }
}
finally {
    if ([string]::IsNullOrWhiteSpace($PreviousPythonPath)) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    else {
        $env:PYTHONPATH = $PreviousPythonPath
    }

    if ([string]::IsNullOrWhiteSpace($PreviousCleanFlag)) {
        Remove-Item Env:OSM_SCI_CLEAN_ENV -ErrorAction SilentlyContinue
    }
    else {
        $env:OSM_SCI_CLEAN_ENV = $PreviousCleanFlag
    }
}

if (-not (Test-Path -LiteralPath $SmokeReport -PathType Leaf)) {
    throw "The packaged executable did not create its smoke-test report: $SmokeReport"
}

$Smoke = Get-Content -LiteralPath $SmokeReport -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Smoke.status -ne "success") {
    throw "The packaged executable smoke report did not report success."
}
if ([int]$Smoke.five_step_pages -ne 5) {
    throw "The packaged GUI reported an unexpected page count: $($Smoke.five_step_pages)"
}
if (-not [bool]$Smoke.frozen) {
    throw "The startup smoke test did not execute in frozen mode."
}

Write-Host "[7/9] Copying documentation, licences, examples and smoke evidence..."
$ReleaseFiles = @(
    "README.md",
    "README_CN.md",
    "README_EN.md",
    "QUICK_START_EN.md",
    "QUICK_START_CN.md",
    "LICENSE",
    "Licence.txt",
    "CITATION.cff",
    "THIRD_PARTY_NOTICES.md",
    "OSM_ATTRIBUTION_AND_ODBL.md",
    "CHANGELOG.md"
)

foreach ($RelativeFile in $ReleaseFiles) {
    $SourceFile = Join-Path $Repo $RelativeFile
    if (-not (Test-Path -LiteralPath $SourceFile -PathType Leaf)) {
        throw "Required release file is missing: $SourceFile"
    }
    Copy-Item -LiteralPath $SourceFile -Destination $Built -Force
}

$Examples = Join-Path $Repo "examples"
if (-not (Test-Path -LiteralPath $Examples -PathType Container)) {
    throw "Examples directory is missing: $Examples"
}
Copy-Item -LiteralPath $Examples -Destination $Built -Recurse -Force

$ValidationDirectory = Join-Path $Built "validation"
New-Item -ItemType Directory -Path $ValidationDirectory -Force | Out-Null
Copy-Item -LiteralPath $SmokeReport -Destination $ValidationDirectory -Force

$BuildInfo = [ordered]@{
    software_version = "0.4.1"
    interface_language = "English"
    python_version = (python --version 2>&1).ToString().Trim()
    gdal_version = (& $Ogr2Ogr --version 2>&1).ToString().Trim()
    qt_version = (
        python -c "from PySide6.QtCore import qVersion; print(qVersion())"
    ).Trim()
    build_time_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    executable = "$AppName.exe"
    gdal_data_directory_in_bundle = "gdal_data"
    proj_data_directory_in_bundle = "proj_data"
    application_resources_in_bundle = "osm_scientific_converter/resources"
    packaged_startup_smoke = "validation/WINDOWS_ENGLISH_STARTUP_SMOKE.json"
    packaged_profiles = @("aeroway", "pipeline", "power")
}
$BuildInfo | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $Built "BUILD_INFO.json") -Encoding UTF8

Write-Host "[8/9] Creating the GitHub Release ZIP..."
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $Built "*") -DestinationPath $ZipPath -CompressionLevel Optimal

if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf)) {
    throw "The release ZIP was not created: $ZipPath"
}

$Hash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$Hash  $(Split-Path -Leaf $ZipPath)" |
    Set-Content -LiteralPath (Join-Path $OutputBase "SHA256_WINDOWS_ENGLISH.txt") -Encoding ascii

Write-Host "[9/9] Build and packaged-startup validation completed successfully." -ForegroundColor Green
Write-Host "Application directory: $Built"
Write-Host "Executable: $Exe"
Write-Host "Startup smoke report: $SmokeReport"
Write-Host "Release ZIP: $ZipPath"
Write-Host "SHA-256: $Hash"

if ([string]::IsNullOrWhiteSpace($PreviousQtPlatform)) {
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
}
else {
    $env:QT_QPA_PLATFORM = $PreviousQtPlatform
}
