# Build a portable folder; model weights and recordings remain beside the EXE.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from pathlib import Path
import sys

datas = [('static', 'static'), ('LICENSE', '.'), ('THIRD_PARTY_NOTICES.md', '.'), ('third-party', 'third-party')]
datas += collect_data_files('reportlab',includes=['fonts/Vera*.ttf','fonts/*license*','fonts/*LICENSE*'])
# This Python distribution ships a certificate-policy PEM used by ssl.py.
certificate_policy = Path(sys.base_prefix) / 'Lib' / 'codex-rejected-cas.pem'
if certificate_policy.is_file():
    datas.append((str(certificate_policy), '.'))
binaries = []
hiddenimports = [
    'app.server', 'app.pipeline', 'app.speakers', 'uvicorn.logging',
    'uvicorn.loops.asyncio', 'uvicorn.protocols.http.h11_impl',
    'uvicorn.lifespan.on', 'sklearn.cluster._agglomerative',
]
for package in ('faster_whisper', 'sherpa_onnx', 'sherpa_onnx_core', 'soundfile', 'ctranslate2', 'onnxruntime'):
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)
    hiddenimports += collect_submodules(package)

a = Analysis(['desktop.py'], pathex=[], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
    excludes=['pypdf', 'pytest', 'tkinter', 'matplotlib', 'IPython', 'notebook', 'torch', 'torchaudio',
              'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.Qt3DCore'], noarchive=False)
# Qt uses Windows' unversioned ICU API. Never bundle a third-party icuuc.dll
# found on PATH (for example Poppler's version-suffixed ICU build).
a.binaries = [item for item in a.binaries if item[0].lower() not in ('icuuc.dll', 'icudt78.dll')]
# Use the exact OpenSSL build that belongs to the bundled Python interpreter.
for dll_name in ('libssl-3-x64.dll', 'libcrypto-3-x64.dll'):
    python_dll = Path(sys.base_prefix) / 'DLLs' / dll_name
    a.binaries = [(dest, str(python_dll), kind) if dest.lower() == dll_name else (dest, source, kind)
                  for dest, source, kind in a.binaries]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Nipahut AI Transcriber',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False, icon='static/app.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Nipahut AI Transcriber')
