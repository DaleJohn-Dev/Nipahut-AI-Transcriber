# Third-party software and models

The app's MIT license covers its original source. It does not replace the licenses or notices of dependencies and model weights. Preserve their notices when redistributing binaries or weights. Installation fetches them from their upstream distributions; local model-license files are retained under `models/`.

| Component | License | Upstream |
| --- | --- | --- |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| Whisper / converted base and small weights | MIT | https://github.com/openai/whisper ; https://huggingface.co/Systran/faster-whisper-base ; https://huggingface.co/Systran/faster-whisper-small |
| Whisper large-v3-turbo CTranslate2 conversion | MIT; converted weights are loaded with CPU INT8 compute | https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| Optional SepFormer WHAMR16k weights and SpeechBrain | Apache-2.0; preserve upstream license and attribution | https://huggingface.co/speechbrain/sepformer-whamr16k ; https://github.com/speechbrain/speechbrain |
| Community SepFormer WHAMR FP32 ONNX conversion | Apache-2.0 according to conversion model card; not an official SpeechBrain export | https://huggingface.co/tonythethompson/SepFormer-WhamR16k-ONNX |
| sherpa-onnx | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| pyannote segmentation 3.0 weights | MIT | https://huggingface.co/pyannote/segmentation-3.0 |
| ONNX conversion of segmentation | See retained model MIT license; sherpa runtime Apache-2.0 | https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html |
| WeSpeaker / VoxCeleb ResNet34 ONNX distribution | Apache-2.0 upstream toolkit; preserve upstream model notices | https://github.com/wenet-e2e/wespeaker ; https://github.com/k2-fsa/sherpa-onnx/releases/tag/speaker-recongition-models |
| 3D-Speaker CAM++ bilingual and ERes2NetV2 speaker embedding weights | Apache-2.0; preserve the downloaded model license | https://github.com/modelscope/3D-Speaker |
| Optional Qwen3-ASR-0.6B INT8 evaluation export | Apache-2.0; evaluated separately from the introduction text model | https://huggingface.co/Qwen/Qwen3-ASR-0.6B ; https://k2-fsa.github.io/sherpa/onnx/qwen3-asr/pretrained.html |
| Optional Gemma 4 E2B Q4_0 text weights | Apache-2.0; Google original weights, ggml-org GGUF conversion | https://huggingface.co/google/gemma-4-E2B-it ; https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF |
| Qwen3 0.6B Q8 weights | Apache-2.0 | https://huggingface.co/Qwen/Qwen3-0.6B-GGUF |
| llama.cpp CPU runtime, pinned b9000 | MIT | https://github.com/ggml-org/llama.cpp |
| FastAPI / Pydantic | MIT | https://github.com/fastapi/fastapi ; https://github.com/pydantic/pydantic |
| Uvicorn / Starlette | BSD-3-Clause | https://github.com/encode/uvicorn ; https://github.com/encode/starlette |
| PyAV | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| FFmpeg libraries bundled by the PyAV wheel | LGPL/GPL family, dependent on build configuration; retain wheel notices | https://ffmpeg.org/legal.html |
| SoundFile / libsndfile | BSD-3-Clause / LGPL-2.1-or-later | https://github.com/bastibe/python-soundfile ; https://github.com/libsndfile/libsndfile |
| NumPy / SciPy / scikit-learn | BSD family, with additional bundled-library notices | https://numpy.org ; https://scipy.org ; https://scikit-learn.org |
| Pillow | MIT-CMU and bundled-library notices | https://github.com/python-pillow/Pillow |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| HTTPX | BSD-3-Clause | https://github.com/encode/httpx |
| Frontend icons | Original simple SVG paths, app MIT license | static/index.html |
| Qt / PySide6 / Qt WebEngine | LGPL-3.0 / GPL options and Chromium third-party notices; this build uses the open-source distribution and dynamically linked Qt libraries | https://doc.qt.io/qtforpython-6/ ; https://doc.qt.io/qt-6/qtwebengine-licensing.html |
| Shiboken6 | LGPL-3.0 / GPL options | https://doc.qt.io/qtforpython-6/ |
| PyInstaller build tool and bootloader | GPL-2.0-or-later with exception permitting bundled applications under their own licenses | https://pyinstaller.org/en/stable/license.html |

Transitive libraries keep their original distribution license files in the Python environment. `scripts/license_inventory.py` exports installed distribution versions, license metadata, and a copy of supplied license/notice files into `third-party/`. `requirements-lock.txt` records the tested dependency versions; pytest and its supporting tools are development dependencies.

All selected software is open source, but model weights and their training datasets are separate artifacts. Open model licensing is not a claim that every training datum has been published. Regional-language performance must be evaluated separately.

PDF export uses ReportLab (BSD), https://www.reportlab.com/opensource/. Bundled Bitstream Vera fonts retain their open font license under the reportlab/fonts distribution.

## Model installation and attribution

Weights are not rehosted in this source repository. `setup.ps1 -Desktop -DownloadModels` explicitly downloads the selected models from the upstream sources above into the local ignored `models/` folder. Whisper downloads resolve a Hugging Face repository revision before fetching its files. Downloads record SHA-256 hashes in each model manifest. An existing installation is reused; inference itself uses local files only. Public model downloads do not require entering a Hugging Face token in this app.

Full upstream license texts for Whisper, pyannote segmentation, WeSpeaker, 3D-Speaker, Qwen and llama.cpp are retained under `third-party/Whisper/` and `third-party/model-notices/`. Retain attribution and notices when redistributing weights or runtimes. The MIT license for this application's original code does not relicense those components.

Qwen3 0.6B is an optional **text** model for introduction analysis. Qwen3-ASR and Nemotron research downloads are not installed by the standard setup and are not presented as integrated production models. Their local evaluation artifacts and private benchmark results are excluded from this repository.

## Qt, FFmpeg and binary distribution

The original application code is MIT licensed. Qt/PySide6 and Qt WebEngine are separate dependencies with LGPL/GPL and third-party terms. This project uses their open-source licensing option, keeps the Qt libraries dynamically linked and replaceable, and does not claim that bundling them makes them MIT licensed. Full LGPL-3.0 and GPL-3.0 texts are in `third-party/Qt-open-source/`. Commercial-license notices included by the upstream wheel are preserved as upstream material; this project does not claim to hold a commercial Qt license.

Qt source and licensing: https://code.qt.io/cgit/qt/ ; https://code.qt.io/cgit/pyside/pyside-setup.git/ ; https://doc.qt.io/qtforpython-6/licenses.html . Distributors must preserve the notices for the exact Qt/Chromium build and fulfill applicable source availability, modification and relinking obligations. PyAV/FFmpeg and libsndfile similarly retain their own licenses and source requirements. Recheck the exact wheel/build configuration before publishing compiled binaries; a source-only publication audit is not a binary compliance certification.

Development-only dependencies (including pytest and pypdf) are listed in `requirements-dev.txt` and the generated inventory. Application icon artwork was generated for this project; it is an original nipa hut/speaker illustration and contains no HandBrake logo assets. README screenshots contain fictional demonstration content.

## v0.2 experimental overlap separator

Optional FP32 ONNX model: `tonythethompson/SepFormer-WhamR16k-ONNX`, revision `3f43d502c36e3c26747350d44aeb487615ed01a5`, file `sepformer.onnx`, SHA-256 `d1e5ed49b7cc09e2c5946ce710fec33692b13a69c9c40441b0b14120cb649553`. Upstream checkpoint is `speechbrain/sepformer-whamr16k`; the converter states source revision `21a5b500c6f52fddc387c5d9e5fb13ffd6f039c5`. Retained source license and conversion model card are under `third-party/SpeechBrain/`. Only the separator is downloaded; the conversion's bundled OSD model is not used. Runtime is the already-declared ONNX Runtime, not SpeechBrain/PyTorch. Preserve both upstream attribution and conversion provenance. Model weights are downloaded to ignored local storage and are not relicensed as application MIT code.

Gemma is optional text readability inference. The application downloads only the Q4_0 weights from pinned conversion revision `6938c58e698502037401a5f19f6905f2fb2f7dee`, the conversion model card, the Apache-2.0 license text and MIT llama.cpp b9000 runtime/license. Weight SHA-256: `8e30dff3ac4c8434c49a7036fa15564bdbb6044e42bf04550bf1a096ad7e6a52`. The Windows CPU runtime ZIP is verified against release SHA-256 `8294e287933d3212aa93a32e1ceb800722bede14d9692d405679d4ba77cf05db`. This use does not add or redistribute Gemma 3/3n models under their separate Gemma terms. Google and ggml-org do not endorse this application.
