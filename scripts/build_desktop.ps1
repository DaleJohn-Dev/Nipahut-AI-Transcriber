param([switch]$UpdateExisting)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $projectRoot
# Avoid resolving unrelated DLLs from developer tools on the machine's PATH.
$originalBuildPath = $env:PATH
$env:PATH = ((Join-Path $projectRoot '.venv/Scripts'), "$env:SystemRoot/System32", $env:SystemRoot) -join ';'
& .venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath .desktop-build/dist --workpath .desktop-build/work NipahutAITranscriber.spec
$env:PATH = $originalBuildPath
if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed.' }
$bundleRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '.desktop-build/dist/Nipahut AI Transcriber'))
if (-not $bundleRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Build path is outside the project.' }
$exeTarget = Join-Path $projectRoot 'Nipahut AI Transcriber.exe'
$legacyExeTarget = Join-Path $projectRoot 'Audio Workspace.exe'
$runtimeTarget = Join-Path $projectRoot '_internal'
if ((Test-Path -LiteralPath $exeTarget) -or (Test-Path -LiteralPath $legacyExeTarget) -or (Test-Path -LiteralPath $runtimeTarget)) {
    if (-not $UpdateExisting) { throw 'Use -UpdateExisting to preserve the old bundle and install the new one.' }
    $running = Get-Process -Name 'Audio Workspace','Nipahut AI Transcriber' -ErrorAction SilentlyContinue
    if ($running) { throw 'Close Nipahut AI Transcriber before replacing the executable.' }
    $backupRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot ('.desktop-build/previous-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))))
    if (-not $backupRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Backup path is outside the project.' }
    New-Item -ItemType Directory -Path $backupRoot | Out-Null
    if (Test-Path -LiteralPath $exeTarget) { Move-Item -LiteralPath $exeTarget -Destination $backupRoot }
    if (Test-Path -LiteralPath $legacyExeTarget) { Move-Item -LiteralPath $legacyExeTarget -Destination $backupRoot }
    if (Test-Path -LiteralPath $runtimeTarget) { Move-Item -LiteralPath $runtimeTarget -Destination $backupRoot }
    Write-Host "Previous bundle retained at: $backupRoot"
}
Move-Item -LiteralPath (Join-Path $bundleRoot 'Nipahut AI Transcriber.exe') -Destination $exeTarget
Move-Item -LiteralPath (Join-Path $bundleRoot '_internal') -Destination $runtimeTarget
Write-Host "Desktop executable: $exeTarget"
