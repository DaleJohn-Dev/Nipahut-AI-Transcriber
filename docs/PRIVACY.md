# Local data and publication boundaries

Nipahut AI Transcriber runs transcription and speaker analysis on the computer. It does not send recordings to a hosted transcription service. Model installation downloads files from Hugging Face and official upstream release servers; those servers receive normal download requests. An internet connection is needed for the first installation of dependencies and models.

## What stays on the computer

`data/` contains imported recordings, decoded audio, optional cleaned audio, transcripts, speaker reference selections, manual corrections, settings and saved result revisions. Speaker embeddings and reference audio may be sensitive. The application does not provide voice authentication or a verified identity database.

Optional overlap review writes only the selected two-source preview clips under that recording's local `separations/` directory. These files and their manual assignments are also excluded from GitHub. No audio is sent to Hugging Face; that service is used only for explicit model downloads.

The native desktop window uses a loopback-only local engine and an embedded renderer. This does not encrypt files at rest: normal Windows file permissions and disk protection still matter. Exports contain the transcript and speaker labels the user chooses to export.

## What belongs in GitHub

Only application source, fictional test fixtures, dependency declarations, license notices and explicitly prepared demo screenshots belong in this repository. The following are excluded:

- All recordings, transcripts, voice references, personal settings and result revisions in `data/`.
- Downloaded model weights and runtimes in `models/`.
- Local reports, handoff notes, generated transcript PDFs, logs and screenshots in `test-results/`, `output/` and `.cache/`.
- Credentials, environment files, virtual environments, desktop executables and generated build folders.
- Machine-specific research scripts referring to private recording IDs.

The public screenshot uses fictional participants and demonstration audio. It is not a benchmark or evidence of diarization accuracy.

Before publishing a change, run `python scripts/audit_public_files.py`. The audit checks the exact Git index (the files about to be committed), rather than relying only on `.gitignore`. It is a practical check, not a guarantee that arbitrary future content is safe to publish.

Optional Gemma punctuation review sends recognized text only to a local llama.cpp process on 127.0.0.1:8767. Downloading the model requires internet; inference does not. One latest suggestion and accepted grouped-answer edits are saved with the local recording, while original segments remain intact. Auto-scroll preference is local.
