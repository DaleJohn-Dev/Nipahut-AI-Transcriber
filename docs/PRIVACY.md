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

Writing modes are separate: punctuation keeps recognized words; grammar can replace words; sentence completion can propose an ending. Proposed additions/removals are shown for review and remain drafts until explicitly saved. Accepted AI text is labelled as reviewed, while the original segments remain local and preserved.


## Persistent local voice profiles

The optional voice library stores reviewed names and numerical speaker embeddings in `data/voice-profiles.json`. These are sensitive voice data, stored locally in plaintext under normal Windows file permissions. No recording copy is added by enrollment. Each profile is tied to the actual embedding model hash; incompatible models are not compared. Up to five explicitly reviewed samples are retained per name/model. New matches are suggestions and never update the saved voice automatically. Use Settings → Voice library to disable matching or delete a fingerprint. Deletion leaves existing transcripts unchanged. The entire `data/` folder, including this library, is excluded from GitHub and the staged publication audit rejects it.

Private classifier comparison reports and proposed timelines remain in excluded `test-results/`; they are not public benchmarks. Synthetic classifier tests use fictional vectors and do not establish accuracy on user recordings.
