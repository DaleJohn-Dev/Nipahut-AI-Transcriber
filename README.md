<p align="center"><img src="static/nipahut-icon.png" width="100" alt="Nipahut AI Transcriber: a nipa hut with a speaker"></p>

<h1 align="center">Nipahut AI Transcriber</h1>
<p align="center"><strong>Your conversations. Your computer.</strong><br>Local transcription, speaker diarization, and a workspace for careful human review.</p>
<p align="center">Windows desktop · Multilingual · Offline inference · MIT application source</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-087d86" alt="Application license MIT"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20x64-3063a3" alt="Windows x64">
  <img src="https://img.shields.io/badge/inference-local-087d86" alt="Local inference">
  <img src="https://img.shields.io/badge/status-development%20preview-ad7512" alt="Development preview">
</p>

<p align="center"><a href="#built-for-reviewing-real-conversations">Features</a> · <a href="#install-the-development-package">Quickstart</a> · <a href="#choose-the-models-you-need">Models</a> · <a href="docs/PRIVACY.md">Privacy</a> · <a href="CONTRIBUTING.md">Contributing</a></p>

Turn meetings, interviews, and focus-group recordings into readable, speaker-labelled transcripts—without sending audio to a cloud transcription service. See where each person speaks, check their introduction, listen to detected solo sections, and export a transcript you can work with.

> **Development preview.** Transcripts and speaker identities need review. The app does not promise error-free transcription, verified identity, or ten-way voice separation.

![Nipahut AI Transcriber workspace](docs/images/workspace-light.png)

*Actual application interface with fictional participants and locally synthesized demonstration audio. The displayed transcript is an authored UI fixture, not an accuracy benchmark. No private recording is shown.*

## Built for reviewing real conversations

| Feature | What you can do |
| --- | --- |
| Local transcription | Multilingual Whisper through faster-whisper/CTranslate2 with CPU INT8 compute. |
| Speaker activity | Aligned lanes, simultaneous intervals, timestamps and uncertain assignments. |
| Introduction names | Suggest names from opening self-introductions, then confirm or correct them. |
| Voice references | Anchor labels with clean reference clips and optionally cross-check uncertain clean regions with a second embedding model. |
| Spectral inspection | Inspect time, frequency and signal strength in the recording and speaker samples. |
| Playback | Play/pause, stop, skip ±10 seconds, 1×–2× speed, and review a speaker's detected solo sections. |
| Targeted edits | Select a lane range and right-click to silence or restore detected solo activity while retaining the original. |
| Transcript review | Search, edit text, rename speakers and correct assignments. |
| Useful exports | Plain PDF, TXT, SRT subtitles, JSON and RTTM speaker activity. |
| Compact workspace | Overlay settings, light/dark themes, model load/unload and a slim processing status row. |

Optional denoise, dehiss, hum filtering and normalization are available. Cleaning can also remove useful speech cues, so compare the original before relying on it for difficult audio.

## Install the development package

Requires **Windows x64**, **Python 3.12**, and Git. Internet access is needed to install dependencies and download models; installed inference runs offline. Node.js is optional for JavaScript development checks.

```powershell
git clone https://github.com/DaleJohn-Dev/Nipahut-AI-Transcriber.git
cd Nipahut-AI-Transcriber
.\setup.ps1 -Desktop -DownloadModels
& ".\Start Nipahut AI Transcriber.cmd"
```

This installs the desktop dependencies and downloads Whisper small, shared segmentation/WeSpeaker, CAM++ and the independent ERes2Net verifier. In Settings, select **CAM++** for speaker diarization and enable or disable the independent check as needed. Existing model folders are reused.

Whisper and optional Qwen weights download directly from **Hugging Face**. Speaker models and native runtimes use their **official upstream releases**. Weights are not committed to Git or copied into a second Hugging Face cache. No Hugging Face token or hosted inference account is required for the configured public downloads.

### Choose the models you need

```powershell
# Smaller transcription model for constrained computers
.\setup.ps1 -Desktop -DownloadModels -AsrModel whisper-base

# Larger Whisper model; more disk/RAM and potentially longer CPU processing
.\setup.ps1 -Desktop -DownloadModels -AsrModel whisper-turbo

# Optional local text model for introduction-name analysis
.\setup.ps1 -Desktop -DownloadModels -IncludeNameModel

# Preview sources and approximate sizes without downloading
.\.venv\Scripts\python.exe scripts/download_models.py --plan
```

| Download | Approximate local model space | Purpose |
| --- | --- | --- |
| Whisper base / small / turbo | 150 MB / 490 MB / 1.65 GB | Choose one ASR model to start. |
| Shared diarization + CAM++ + ERes2Net | 140 MB | Segmentation, voice embeddings and an independent check. |
| Optional Qwen3 0.6B + llama.cpp | 680 MB | Text analysis of introductions; not an audio ASR model. |

Python/Qt dependencies and recordings need additional space. Downloads reserve at least 3 GB of free space. Settings shows model sizes and free disk space; unused models can be removed there. Exact sizes depend on the upstream artifact.

## From recording to reviewed transcript

1. Import or drop audio. AAC, WAV, MP3, M4A, FLAC, OGG, OPUS, MP4, WEBM and WMA are accepted subject to the installed PyAV codecs.
2. Choose language, models and participant count in Settings. Let participants introduce themselves individually near the start when possible.
3. Transcribe. Follow preparation, optional cleanup, transcription, diarization and name analysis in the progress row.
4. Review names, uncertain turns and overlaps. Voice samples and timestamps provide evidence to check—not proof of identity.
5. Correct labels or text, then export PDF, TXT, SRT, JSON or RTTM.

The per-recording count supports auto detection or 1–20 participants. Original uploads and decoded audio are retained. Reprocessing archives the previous result; speaker-only updates reuse cached word timestamps when available.

## Languages and practical limits

English and Filipino/Tagalog use Whisper's supported language modes. **Taglish** uses automatic detection plus a Filipino/English hint. **Cebuano/Bisaya and Bicolano/Bikol are experimental**, with hints rather than dedicated Whisper language tokens. Names, regional speech, distant microphones and code switching need human review.

The current segmentation model detects at most **two simultaneous voices**. A meeting may contain ten participants, but that does not mean the app can separate ten people speaking at once. Lanes retain simultaneous intervals; mixed words are marked for review instead of copied into invented individual transcripts.

Speaker-lane playback skips detected overlaps to review solo sections. It **does not extract an isolated voice from overlapping speech**. Missed overlaps or incorrect labels can still include another voice. Speaker-only silencing during overlap is blocked until separated tracks are available.

Spectrograms visualize sound; they are not unique biometric fingerprints. Embeddings help match voices within a recording and do not provide verified identity or voice authentication. No full-recording minimal error rate is claimed without a human-labelled reference.

## Open source, attribution and privacy

The application's original source is [MIT licensed](LICENSE). Third-party software and weights retain their own licenses, including MIT, Apache-2.0, BSD and LGPL/GPL terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), the full texts in [third-party/](third-party/), and its generated dependency inventory. The app's license does not replace those obligations.

Recordings, transcripts, voice references, personal settings, local reports, credentials and build output are excluded from this repository. Installation makes normal requests to upstream download servers; transcription and speaker inference use local files. Read [the privacy and publication boundaries](docs/PRIVACY.md).

## Develop and build

```powershell
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
node --check static/app.js
node --check static/clip-controls.js
node tests/player_controls.test.cjs

# Build the Windows desktop folder bundle
.\scripts\build_desktop.ps1
```

Close the app and use `-UpdateExisting` to replace an existing build while retaining a rollback. The portable package needs **Nipahut AI Transcriber.exe**, **_internal/** and its adjacent **models/** and **data/** folders. The source repository does not contain a prebuilt EXE.

The native Qt window embeds the single-page interface and a loopback-only FastAPI engine. Native speaker inference runs in a separate process to keep the parent responsive. A local text-only Qwen service is optional. PyTorch and CUDA are not required by the configured ONNX/CTranslate2 stack.

| Directory | Responsibility |
| --- | --- |
| `app/` | Audio, ASR, diarization, references, exports, storage and local API. |
| `static/` | Interface, player, spectrogram controls and branding. |
| `desktop.py` | Native window, engine lifecycle and file dialogs. |
| `scripts/` | Setup, downloads, packaging, synthetic demos and developer checks. |
| `tests/` | Synthetic/unit fixtures; no user recordings. |
| `third-party/` | Attribution and retained upstream license texts. |

To refresh notices, run `scripts/license_inventory.py` and `scripts/retain_model_notices.py`. Before publishing, stage reviewed source and run `scripts/audit_public_files.py`.

Contributions are welcome: clear reproductions, privacy-safe synthetic fixtures, measured speaker-error reductions and improvements for Filipino and regional-language speech are especially useful. Never attach someone else's private recording or voice reference to a public issue.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and evidence expected for accuracy changes.
