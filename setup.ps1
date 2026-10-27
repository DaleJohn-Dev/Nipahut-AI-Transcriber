param(
    [switch]$DownloadModels,
    [switch]$Desktop,
    [ValidateSet('whisper-base','whisper-small','whisper-turbo')]
    [string]$AsrModel = 'whisper-small',
    [switch]$IncludeNameModel,
    [switch]$IncludeSeparationModel
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { python -m venv .venv }
& .venv/Scripts/python.exe -m pip install --no-cache-dir -r requirements.txt -c requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if ($Desktop) {
  & .venv/Scripts/python.exe -m pip install --no-cache-dir -r requirements-desktop.txt -c requirements-lock.txt
  if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
}
if ($DownloadModels) {
    $modelSelection = @($AsrModel, 'diarization-campplus', 'diarization-eres2net')
    if ($IncludeNameModel) { $modelSelection += 'qwen-0.6b' }
    if ($IncludeSeparationModel) { $modelSelection += 'sepformer-whamr' }
    Write-Host 'Installing selected models directly from Hugging Face and official upstream releases.'
    & .venv/Scripts/python.exe scripts/download_models.py @modelSelection
  if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
}
Write-Host 'Ready. Run Start Nipahut AI Transcriber.cmd.'
