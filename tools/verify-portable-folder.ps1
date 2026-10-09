#Requires -Version 7.2
<#
Static checks of a built Quiz Reporter portable folder and/or its zip. Nothing is started.

  verify-portable-folder.ps1 -Folder dist\Quiz-Reporter-v1.0.0
  verify-portable-folder.ps1 -Zip dist\Quiz-Reporter-v1.0.0-windows.zip
  verify-portable-folder.ps1 -Folder <folder> -Zip <zip>      (also compares their file lists)

Exit code 0 when every check passed, 1 otherwise. Run it on a folder that was never started:
a started program leaves Data, logs and a lock file behind, which this script reports as failures.
#>
[CmdletBinding()]
param(
    [string]$Folder = '',
    [string]$Zip = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $Folder -and -not $Zip) {
    Write-Error 'Give -Folder, -Zip, or both.'
    exit 2
}

$repository = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$initText = Get-Content -LiteralPath (Join-Path $repository 'src\quiz_reporter\__init__.py') -Raw -Encoding utf8
if ($initText -notmatch '(?m)^__version__\s*=\s*"(\d+\.\d+\.\d+)"') { Write-Error 'cannot read __version__'; exit 2 }
$version = $Matches[1]
$releaseName = "Quiz-Reporter-v$version"

# Keep these in step with packaging\Quiz_Reporter.spec (a unit test compares them).
# Qt modules the program uses: the DLL names (Qt6<Name>.dll) and the Python modules (Qt<Name>.pyd).
$QtKeepDll = @('Core', 'Gui', 'Widgets', 'Svg')
$QtKeepPyd = @('Core', 'Gui', 'Widgets')
# Qt add-ons that are GPL-only in the open-source edition; named in the failure message.
$QtGplOnly = '^(Charts|DataVisualization|VirtualKeyboard|Quick3D|Graphs|Lottie|HttpServer|NetworkAuth)'
# Single files and plugin folders that the spec drops.
$DroppedFiles = @('opengl32sw.dll', 'd3dcompiler_47.dll', 'qpdf.dll', 'qtvirtualkeyboardplugin.dll', 'qtuiotouchplugin.dll')
$DroppedPluginDirs = @('designer', 'multimedia', 'networkinformation', 'position', 'qmltooling', 'scxmldatamodel', 'sensors', 'sqldrivers', 'texttospeech', 'tls', 'webview')
$RuntimeNames = @('Data', 'logs', 'update.json', 'config.json', '.quiz-reporter.lock', 'FORMAT.json')
$StudentDataExtensions = @('.csv', '.tsv', '.xlsx', '.xlsm', '.pdf')

$script:results = [Collections.Generic.List[object]]::new()
function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
    $script:results.Add([PSCustomObject]@{ Name = $Name; Ok = $Ok; Detail = $Detail })
}
function Rel([string]$Root, [string]$Path) { return [IO.Path]::GetRelativePath($Root, $Path).Replace('\', '/') }

function Test-Folder([string]$Root, [string]$Label) {
    $exe = Join-Path $Root 'Quiz Reporter.exe'
    $internal = Join-Path $Root '_internal'
    Check "${Label}: Quiz Reporter.exe exists" (Test-Path -LiteralPath $exe -PathType Leaf) $exe
    Check "${Label}: _internal exists" (Test-Path -LiteralPath $internal -PathType Container) $internal
    foreach ($name in @('LICENSE.md', 'THIRD_PARTY_NOTICES.txt')) {
        $path = Join-Path $Root $name
        $present = (Test-Path -LiteralPath $path -PathType Leaf) -and ((Get-Item -LiteralPath $path).Length -gt 0)
        Check "${Label}: $name beside the EXE" $present $path
    }
    $noticesPath = Join-Path $Root 'THIRD_PARTY_NOTICES.txt'
    if (Test-Path -LiteralPath $noticesPath -PathType Leaf) {
        $noticeText = Get-Content -LiteralPath $noticesPath -Raw -Encoding utf8
        $missing = @('PySide6', 'LGPL', 'https://download.qt.io', 'openpyxl', 'et-xmlfile', 'PyInstaller', 'Python Software Foundation') |
            Where-Object { $noticeText -notmatch [regex]::Escape($_) }
        Check "${Label}: THIRD_PARTY_NOTICES.txt names every bundled package" (@($missing).Count -eq 0) ($missing -join ', ')
    }
    if (-not (Test-Path -LiteralPath $internal -PathType Container)) { return }

    $files = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File)
    $items = @(Get-ChildItem -LiteralPath $Root -Recurse -Force)

    $icon = Join-Path $internal 'quiz_reporter\resources\app_icon.svg'
    Check "${Label}: app_icon.svg inside the bundle" (Test-Path -LiteralPath $icon -PathType Leaf) '_internal/quiz_reporter/resources/app_icon.svg'

    $plugins = Join-Path $internal 'PySide6\plugins'
    foreach ($plugin in @('platforms\qwindows.dll', 'imageformats\qsvg.dll', 'iconengines\qsvgicon.dll')) {
        Check "${Label}: plugin $plugin" (Test-Path -LiteralPath (Join-Path $plugins $plugin) -PathType Leaf) $plugin
    }

    # Qt modules: only the ones the spec keeps may be present.
    $unexpected = [Collections.Generic.List[string]]::new()
    $gpl = [Collections.Generic.List[string]]::new()
    foreach ($file in $files) {
        if ($file.Name -notmatch '^Qt6?(?<module>[A-Za-z0-9]+?)\.(?<ext>dll|pyd)$') { continue }
        $module = $Matches['module']
        $keep = if ($Matches['ext'] -eq 'dll') { $QtKeepDll } else { $QtKeepPyd }
        if ($module -cin $keep) { continue }
        if ($module -match $QtGplOnly) { $gpl.Add((Rel $Root $file.FullName)) } else { $unexpected.Add((Rel $Root $file.FullName)) }
    }
    Check "${Label}: no GPL-only Qt module" ($gpl.Count -eq 0) ($gpl -join '; ')
    Check "${Label}: no unused Qt module (only Core, Gui, Widgets, Svg)" ($unexpected.Count -eq 0) (($unexpected | Select-Object -First 8) -join '; ')

    $dropped = @($items | Where-Object {
            ($_.Name -in $DroppedFiles) -or
            ($_.PSIsContainer -and $_.Name -in @('qml', 'translations')) -or
            ($_.PSIsContainer -and $_.Name -in $DroppedPluginDirs -and $_.Parent.Name -eq 'plugins') -or
            (-not $_.PSIsContainer -and $_.Extension -eq '.qm')
        } | ForEach-Object { Rel $Root $_.FullName })
    Check "${Label}: no unused Qt plugins, QML, translations or software OpenGL" (@($dropped).Count -eq 0) (($dropped | Select-Object -First 8) -join '; ')

    $runtime = @($items | Where-Object { $_.Name -in $RuntimeNames } | ForEach-Object { Rel $Root $_.FullName })
    Check "${Label}: no Data, logs, update.json, config or lock file" (@($runtime).Count -eq 0) ($runtime -join '; ')
    $student = @($files | Where-Object { $_.Extension.ToLowerInvariant() -in $StudentDataExtensions } | ForEach-Object { Rel $Root $_.FullName })
    Check "${Label}: no .csv/.tsv/.xlsx/.xlsm/.pdf anywhere" (@($student).Count -eq 0) (($student | Select-Object -First 8) -join '; ')
    $links = @($items | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } | ForEach-Object { Rel $Root $_.FullName })
    Check "${Label}: no symbolic links or junctions" (@($links).Count -eq 0) ($links -join '; ')

    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        $info = (Get-Item -LiteralPath $exe).VersionInfo
        Check "${Label}: FileVersion is $version" ($info.FileVersion -eq $version) "$($info.FileVersion)"
        Check "${Label}: ProductVersion is $version" ($info.ProductVersion -eq $version) "$($info.ProductVersion)"
        $parts = $version.Split('.')
        Check "${Label}: numeric file version is $version.0" (
            ($info.FileMajorPart -eq [int]$parts[0]) -and ($info.FileMinorPart -eq [int]$parts[1]) -and ($info.FileBuildPart -eq [int]$parts[2])) (
            "$($info.FileMajorPart).$($info.FileMinorPart).$($info.FileBuildPart).$($info.FilePrivatePart)")
        Check "${Label}: ProductName is Quiz Reporter" ($info.ProductName -eq 'Quiz Reporter') "$($info.ProductName)"
        # The Korean text is checked by shape only; this script stays ASCII.
        $description = "$($info.FileDescription)"
        Check "${Label}: FileDescription is set (Korean)" (($description.Length -gt 10) -and ($description -match '[^\x00-\x7F]')) $description
        Check "${Label}: CompanyName names the author" ("$($info.CompanyName)" -like '*Cho, Seung-Hyun*') "$($info.CompanyName)"
        Check "${Label}: LegalCopyright names the license" (("$($info.LegalCopyright)" -like '*2026*') -and ("$($info.LegalCopyright)" -like '*PolyForm Noncommercial 1.0.0*')) "$($info.LegalCopyright)"
        # The PE subsystem must be "Windows GUI" (2): no console window.
        $bytes = [IO.File]::ReadAllBytes($exe)
        $subsystem = -1
        if ($bytes.Length -gt 0x200 -and $bytes[0] -eq 0x4D -and $bytes[1] -eq 0x5A) {
            $peOffset = [BitConverter]::ToInt32($bytes, 0x3C)
            $subsystem = [BitConverter]::ToUInt16($bytes, $peOffset + 24 + 68)
        }
        Check "${Label}: the EXE is a windowed (no console) program" ($subsystem -eq 2) "subsystem=$subsystem"
    }
}

$temporary = $null
try {
    if ($Folder) {
        $folderPath = (Resolve-Path -LiteralPath $Folder -ErrorAction Stop).Path
        Check "folder is named $releaseName" ((Split-Path $folderPath -Leaf) -eq $releaseName) $folderPath
        Test-Folder $folderPath 'folder'
    }
    if ($Zip) {
        $zipPath = (Resolve-Path -LiteralPath $Zip -ErrorAction Stop).Path
        $zipName = Split-Path $zipPath -Leaf
        Check "zip is named $releaseName-windows.zip" ($zipName -eq "$releaseName-windows.zip") $zipName
        $sidecar = "$zipPath.sha256"
        $haveSidecar = Test-Path -LiteralPath $sidecar -PathType Leaf
        Check 'zip has a .sha256 sidecar' $haveSidecar $sidecar
        if ($haveSidecar) {
            $line = (Get-Content -LiteralPath $sidecar -Raw -Encoding ascii).Trim()
            $shaOk = $line -match '^(?<hash>[0-9a-f]{64})  (?<name>.+)$'
            Check 'sidecar format is "<hex>  <zip name>"' $shaOk $line
            if ($shaOk) {
                $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
                Check 'sidecar names this zip' ($Matches['name'] -eq $zipName) $Matches['name']
                Check 'zip sha256 matches the sidecar' ($Matches['hash'] -eq $actual) $actual
            }
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
        try {
            $entryNames = @($archive.Entries | Where-Object { $_.Name } | ForEach-Object { $_.FullName.Replace('\', '/') })
        } finally { $archive.Dispose() }
        $roots = @($entryNames | ForEach-Object { $_.Split('/')[0] } | Sort-Object -Unique)
        Check "zip holds exactly one top folder, $releaseName" ((@($roots).Count -eq 1) -and ($roots[0] -eq $releaseName)) ($roots -join ', ')
        if ($Folder) {
            $onDisk = @(Get-ChildItem -LiteralPath $folderPath -Recurse -Force -File | ForEach-Object { "$releaseName/" + (Rel $folderPath $_.FullName) })
            $difference = @(Compare-Object ($onDisk | Sort-Object) ($entryNames | Sort-Object))
            Check 'zip and folder hold the same files' ($difference.Count -eq 0) (($difference | Select-Object -First 5 | ForEach-Object { $_.InputObject }) -join '; ')
        }
        if ((@($roots).Count -eq 1) -and ($roots[0] -eq $releaseName)) {
            $temporary = Join-Path ([IO.Path]::GetTempPath()) ('quiz-reporter-verify-' + [guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $temporary | Out-Null
            [IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $temporary)
            Test-Folder (Join-Path $temporary $releaseName) 'zip'
        }
    }
} finally {
    if ($temporary) {
        $base = ([IO.Path]::GetFullPath([IO.Path]::GetTempPath())).TrimEnd('\', '/')
        $parent = ([IO.Path]::GetDirectoryName($temporary)).TrimEnd('\', '/')
        if (($parent -eq $base) -and ((Split-Path $temporary -Leaf) -like 'quiz-reporter-verify-*') -and (Test-Path -LiteralPath $temporary)) {
            Remove-Item -LiteralPath $temporary -Recurse -Force
        }
    }
}

foreach ($result in $script:results) {
    $mark = if ($result.Ok) { 'OK  ' } else { 'FAIL' }
    $detail = if ($result.Detail) { "  [$($result.Detail)]" } else { '' }
    Write-Host "$mark $($result.Name)$detail"
}
$failed = @($script:results | Where-Object { -not $_.Ok })
if ($failed.Count -gt 0) {
    Write-Host ''
    Write-Host "VERIFY FAILED: $($failed.Count) of $($script:results.Count) checks failed."
    exit 1
}
Write-Host ''
Write-Host "VERIFY PASSED: $($script:results.Count) checks."
exit 0
