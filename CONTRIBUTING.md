# Contributing to Nipahut AI Transcriber

Useful contributions make conversations easier to review while keeping computation local and data private.

## Public access and contribution policy

The repository remains public for viewing, cloning and downloads. Pull requests are disabled during the development preview; changes are maintained by the repository owner. Public bug reports and feature requests can be submitted through Issues, without private recordings or credentials. Do not enable pull requests or change this policy without the owner’s request.

## Start small

Open an issue describing the concrete problem and expected behavior. Include Windows/Python versions, selected models and a minimal reproduction. Use synthetic or explicitly consented, de-identified examples. Never publish personal recordings, transcripts, voice references, credentials or private paths.

## Development checks

Install with `setup.ps1 -Desktop`, then install `requirements-dev.txt` into `.venv`. Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check static/app.js
node --check static/clip-controls.js
node tests/player_controls.test.cjs
```

Real inference smoke checks require explicitly downloaded models. `scripts/create_test_audio.ps1` generates a synthetic fixture using installed Windows voices. The README demonstration can be regenerated with `scripts/create_readme_demo.ps1`; its authored transcript is not inference evidence.

## Accuracy changes need evidence

Distinguish participant count from simultaneous speaker capacity. Do not treat model agreement, introduction matching, or fewer unassigned regions as proof of lower diarization error. When proposing accuracy improvements, provide a human-verified reference, an explicit scoring region, overlap handling, fixed speaker-identity evaluation where relevant, and CPU/RAM/runtime measurements. `scripts/evaluate_reference.py` is available for overlap-aware human-reference scoring.

Preserve uncertain labels, original recordings, manual edits and result revisions. Do not duplicate mixed words into invented per-speaker transcripts. Keep experimental dependencies optional until their licenses, resource use and practical accuracy are assessed.

## Publication checks

Stage only intended source and documentation, then run `python scripts/audit_public_files.py`. Review `git diff --cached` yourself: automated checks do not replace review. Never force-add ignored data, downloaded weights, local reports or environment files. New dependencies require upstream links, version declarations and an update to `THIRD_PARTY_NOTICES.md` with retained notices.

If the owner explicitly enables contributions in the future, contributors submitting original changes agree to license those changes under this project's MIT license. Third-party material keeps its original license and attribution. Do not submit material you do not have permission to contribute.

## Versions and release history

Every published update gets a new version, even a documentation-only update. During this preview series, advance the numeric preview suffix, for example:

```powershell
python scripts/bump_version.py 0.2.0-preview.9 --summary "Describe the user-visible change"
python scripts/check_version.py
```

The helper pins the previous version to its current source commit and creates the next changelog/history entry. Replace the example version with one newer than VERSION. Expand the changelog entry with meaningful behavior, validation and limits. Use Semantic Versioning: minor versions for added capabilities, patches for compatible stable fixes, majors for incompatible changes. Preview builds use `-preview.N`.

After a push to main passes the regression job, GitHub Actions verifies existing immutable tags and publishes the tag/release notes for the current checked commit. Early updates are labelled retrospectively in CHANGELOG.md and linked to commits; they identify the existing source commits and do not imply those versions were previously released. Published tags are never moved. Releases contain source archives and notes; private data and downloaded weights remain excluded.
