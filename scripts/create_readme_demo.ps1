$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$demoFolder = Join-Path (Get-Location) '.cache/readme-demo'
New-Item -ItemType Directory -Path $demoFolder -Force | Out-Null
Add-Type -AssemblyName System.Speech
$speech = New-Object System.Speech.Synthesis.SpeechSynthesizer
$lines = @(
    @{speaker='speaker_00';name='David';voice='Microsoft David Desktop';text='Hi, I am David. Welcome to our community planning meeting.'},
    @{speaker='speaker_01';name='Sarah';voice='Microsoft Zira Desktop';text='Hello, I am Sarah. I will help review the ideas from our discussion.'},
    @{speaker='speaker_00';name='David';voice='Microsoft David Desktop';text='Our first priority is making sure everyone can contribute to the conversation.'},
    @{speaker='speaker_01';name='Sarah';voice='Microsoft Zira Desktop';text='We can review the transcript together and correct any names or speaker labels.'},
    @{speaker='speaker_00';name='David';voice='Microsoft David Desktop';text='The recordings and transcripts stay on this computer. We can export a plain PDF when we are ready.'},
    @{speaker='speaker_01';name='Sarah';voice='Microsoft Zira Desktop';text='That sounds good. Let us keep the next steps clear and easy to share.'}
)
try {
    for ($i=0; $i -lt $lines.Count; $i++) {
        $speech.SelectVoice($lines[$i].voice)
        $speech.SetOutputToWaveFile((Join-Path $demoFolder "voice-$i.wav"))
        $speech.Speak($lines[$i].text)
        $speech.SetOutputToNull()
    }
} finally { $speech.Dispose() }
$lines | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $demoFolder 'demo-lines.json') -Encoding utf8
& .venv/Scripts/python.exe scripts/create_readme_demo.py
if ($LASTEXITCODE -ne 0) { throw 'Demo generation failed' }
