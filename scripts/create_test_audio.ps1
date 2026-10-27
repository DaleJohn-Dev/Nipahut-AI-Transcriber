$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Path 'test-results' -Force | Out-Null
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$lines = @(
    @('Microsoft David Desktop', 'Hello, my name is David. I will lead our product planning meeting today. We are building a local audio application.'),
    @('Microsoft Zira Desktop', 'Hi, I am Sarah. I work on the design team. I would like to make the settings panel simple and clear.'),
    @('Microsoft David Desktop', 'Thank you, Sarah. We should keep all the recordings on this computer. Let us start with transcription and speaker recognition.'),
    @('Microsoft Zira Desktop', 'I agree with that plan. The spectrogram should show the frequency patterns of each speaker. We can test it this evening.')
)
for ($i = 0; $i -lt $lines.Count; $i++) {
    $synth.SelectVoice($lines[$i][0])
    $synth.SetOutputToWaveFile((Join-Path (Get-Location) "test-results/voice-$i.wav"))
    $synth.Speak($lines[$i][1])
    $synth.SetOutputToNull()
}
$synth.Dispose()
& .venv/Scripts/python.exe -c "from app.audio import read_audio,RATE; import numpy as np,soundfile as sf; from pathlib import Path; parts=[]; [parts.extend([read_audio(p),np.zeros(RATE,dtype=np.float32)]) for p in sorted(Path('test-results').glob('voice-*.wav'))]; sf.write('test-results/two-speaker-test.wav',np.concatenate(parts),RATE,subtype='PCM_16')"
Write-Host 'Created synthetic two-speaker test recording.'
