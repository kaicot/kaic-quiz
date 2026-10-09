#Requires -Version 7.2
<#
Builds the Quiz Reporter Windows portable release:
  <DistRoot>\Quiz-Reporter-v<version>\               the onedir folder
  <DistRoot>\Quiz-Reporter-v<version>-windows.zip    the same folder, zipped
  <DistRoot>\Quiz-Reporter-v<version>-windows.zip.sha256

Everything is built in a new folder under WorkRoot, checked with verify-portable-folder.ps1, and
only then moved into DistRoot. Existing outputs are never replaced: remove them first.
#>
[CmdletBinding()]
param(
    [string]$Python = '',
    [string]$DistRoot = '',
    [string]$WorkRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail([string]$Message) { throw "PORTABLE_BUILD_FAILED: $Message" }
function FullPath([string]$PathValue) {
    if ([string]::IsNullOrWhiteSpace($PathValue)) { Fail 'an empty path is not allowed' }
    return [IO.Path]::GetFullPath($PathValue)
}
function Assert-NoReparseAncestor([string]$PathValue, [string]$Label) {
    $current = FullPath $PathValue
    while ($true) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                Fail "$Label must not be, or sit under, a symbolic link or junction: $current"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if (-not $parent -or $parent -eq $current) { break }
        $current = $parent
    }
}

$repository = FullPath (Split-Path $PSScriptRoot -Parent)
if (-not $Python) { $Python = Join-Path $repository '.venv\Scripts\python.exe' }
$Python = FullPath $Python
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { Fail "Python does not exist: $Python" }
if (-not $DistRoot) { $DistRoot = Join-Path $repository 'dist' }
if (-not $WorkRoot) { $WorkRoot = Join-Path $repository 'build' }
$DistRoot = FullPath $DistRoot
$WorkRoot = FullPath $WorkRoot

$spec = Join-Path $repository 'packaging\Quiz_Reporter.spec'
$notices = Join-Path $repository 'packaging\generate_third_party_notices.py'
$verify = Join-Path $PSScriptRoot 'verify-portable-folder.ps1'
$licenseFile = Join-Path $repository 'LICENSE.md'
foreach ($required in @($spec, $notices, $verify, $licenseFile)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { Fail "A required file is missing: $required" }
}

Assert-NoReparseAncestor $repository 'the repository'
Assert-NoReparseAncestor $DistRoot 'DistRoot'
Assert-NoReparseAncestor $WorkRoot 'WorkRoot'

# The version comes from the package; pyproject.toml must say the same.
$initText = Get-Content -LiteralPath (Join-Path $repository 'src\quiz_reporter\__init__.py') -Raw -Encoding utf8
if ($initText -notmatch '(?m)^__version__\s*=\s*"(\d+\.\d+\.\d+)"') { Fail 'could not read __version__ from the package' }
$version = $Matches[1]
$projectText = Get-Content -LiteralPath (Join-Path $repository 'pyproject.toml') -Raw -Encoding utf8
if ($projectText -notmatch '(?m)^version\s*=\s*"(\d+\.\d+\.\d+)"' -or $Matches[1] -ne $version) {
    Fail "the version in pyproject.toml does not match the package version $version"
}

& $Python -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version; import PyInstaller, PySide6, openpyxl'
if ($LASTEXITCODE -ne 0) { Fail 'Python 3.12 with PyInstaller, PySide6 and openpyxl is required' }

$releaseName = "Quiz-Reporter-v$version"
$finalFolder = Join-Path $DistRoot $releaseName
$finalZip = Join-Path $DistRoot "$releaseName-windows.zip"
$finalSidecar = "$finalZip.sha256"
foreach ($path in @($finalFolder, $finalZip, $finalSidecar)) {
    if (Test-Path -LiteralPath $path) { Fail "an output already exists and will not be replaced; remove it first: $path" }
}

New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
$workChild = Join-Path $WorkRoot ('portable-build-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workChild -ErrorAction Stop | Out-Null

$stageDist = Join-Path $workChild 'dist'
$stageFolder = Join-Path $stageDist $releaseName
$stageZip = Join-Path $workChild "$releaseName-windows.zip"
$stageSidecar = "$stageZip.sha256"
$noticeFile = Join-Path $workChild 'THIRD_PARTY_NOTICES.txt'

& $Python $notices $noticeFile
if ($LASTEXITCODE -ne 0) { Fail 'could not generate THIRD_PARTY_NOTICES.txt' }

& $Python -m PyInstaller --noconfirm --clean --distpath $stageDist --workpath (Join-Path $workChild 'pyinstaller') $spec
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed with exit code $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath (Join-Path $stageFolder 'Quiz Reporter.exe') -PathType Leaf)) {
    Fail "PyInstaller did not produce '$releaseName\Quiz Reporter.exe'"
}

# The license and the notices sit beside the EXE, not inside _internal.
Copy-Item -LiteralPath $licenseFile -Destination (Join-Path $stageFolder 'LICENSE.md')
Copy-Item -LiteralPath $noticeFile -Destination (Join-Path $stageFolder 'THIRD_PARTY_NOTICES.txt')

# A release folder is never a place where the program ran; nothing may be a link either.
foreach ($runtimeName in @('Data', 'logs', 'update.json', '.quiz-reporter.lock')) {
    if (Test-Path -LiteralPath (Join-Path $stageFolder $runtimeName)) { Fail "the staged folder contains runtime data: $runtimeName" }
}
$linked = Get-ChildItem -LiteralPath $stageFolder -Recurse -Force |
    Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } | Select-Object -First 1
if ($linked) { Fail "the staged folder contains a link: $($linked.FullName)" }

Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($stageFolder, $stageZip, [IO.Compression.CompressionLevel]::Optimal, $true)
$hash = (Get-FileHash -LiteralPath $stageZip -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($stageSidecar, "$hash  $releaseName-windows.zip`n", [Text.Encoding]::ASCII)

# Check the staged folder and the exact zip bytes before publishing either.
& $verify -Folder $stageFolder -Zip $stageZip
if ($LASTEXITCODE -ne 0) { Fail "the staged release did not pass verify-portable-folder.ps1 (kept for inspection: $workChild)" }

foreach ($path in @($finalFolder, $finalZip, $finalSidecar)) {
    if (Test-Path -LiteralPath $path) { Fail "an output appeared during the build and will not be replaced: $path" }
}
Move-Item -LiteralPath $stageFolder -Destination $finalFolder
Move-Item -LiteralPath $stageZip -Destination $finalZip
Move-Item -LiteralPath $stageSidecar -Destination $finalSidecar

# The work folder is ours (a new child of WorkRoot); it only held the staging copies.
if ((Split-Path $workChild -Parent) -eq $WorkRoot -and (Split-Path $workChild -Leaf) -like 'portable-build-*') {
    Remove-Item -LiteralPath $workChild -Recurse -Force
}

[PSCustomObject]@{
    result = 'BUILT'
    version = $version
    folder = $finalFolder
    exe = (Join-Path $finalFolder 'Quiz Reporter.exe')
    zip = $finalZip
    sha256 = $hash
    sha256_sidecar = $finalSidecar
    folder_mb = [math]::Round((Get-ChildItem -LiteralPath $finalFolder -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    zip_mb = [math]::Round((Get-Item -LiteralPath $finalZip).Length / 1MB, 1)
} | ConvertTo-Json
