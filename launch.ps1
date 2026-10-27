param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$desktopExe = Join-Path $PSScriptRoot 'Nipahut AI Transcriber.exe'
if (Test-Path -LiteralPath $desktopExe) {
    $desktopProcess = Start-Process -FilePath $desktopExe -WorkingDirectory $PSScriptRoot -WindowStyle Normal -PassThru
} else {
    $pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Build the desktop executable, or run setup.ps1 -Desktop first.' }
    $desktopProcess = Start-Process -FilePath $pythonPath -ArgumentList 'desktop.py' -WorkingDirectory $PSScriptRoot -WindowStyle Normal -PassThru
}
$desktopProcess.Id | Set-Content -LiteralPath 'data/desktop.pid'
Write-Host 'Nipahut AI Transcriber is opening in its own desktop window.'
