"""Local-only, atomic recording and preferences storage."""
import json
import os
import shutil
import threading
import time
import sys
from pathlib import Path

RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
ROOT = Path(os.environ.get('AUDIO_WORKSPACE_HOME') or (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCE_ROOT))
DATA = ROOT / 'data'
MODELS = ROOT / 'models'
RECORDINGS = DATA / 'recordings'
for directory in (DATA, MODELS, RECORDINGS):
    directory.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()
DEFAULTS = {
    'theme': 'light', 'asr_model': 'whisper-small', 'speaker_model': 'diarization',
    'name_model': 'rules', 'language': 'auto', 'detect_names': True,
    'introduction_seconds': 90, 'speaker_count': 0, 'cluster_threshold': 0.5,
    'cleanup': {'denoise': False, 'dehiss': False, 'hum': 'off', 'normalize': False, 'strength': 0.35},
    'diarization_audio': 'original', 'auto_unload': True,
    'verify_uncertain_speakers': True,
}

def read_json(path, default=None):
    with LOCK:
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return default

def write_json(path, value):
    with LOCK:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        # Windows may briefly hold the file for indexing or antivirus scanning.
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(.03)

def settings():
    saved = read_json(DATA / 'settings.json', {})
    return {**DEFAULTS, **saved, 'cleanup': {**DEFAULTS['cleanup'], **saved.get('cleanup', {})}}

def recording_path(rid):
    if not rid or len(rid) != 32 or any(c not in '0123456789abcdef' for c in rid):
        raise ValueError('Invalid recording ID')
    path = RECORDINGS / rid
    if not path.is_dir():
        raise FileNotFoundError('Recording not found')
    return path

def get_recording(rid):
    return read_json(recording_path(rid) / 'recording.json')

def save_recording(rec):
    write_json(recording_path(rec['id']) / 'recording.json', rec)

def list_recordings():
    records = [read_json(p) for p in RECORDINGS.glob('*/recording.json')]
    return sorted([r for r in records if r], key=lambda r: r['created_at'], reverse=True)

def directory_bytes(path):
    total = 0
    for f in path.rglob('*'):
        try:
            if f.is_file():
                total += f.stat().st_size
        except FileNotFoundError:
            pass
    return total

def disk_info():
    usage = shutil.disk_usage(ROOT)
    return {'free_bytes': usage.free, 'total_bytes': usage.total,
            'models_bytes': directory_bytes(MODELS), 'recordings_bytes': directory_bytes(RECORDINGS)}

def require_space(needed=0):
    if shutil.disk_usage(ROOT).free < needed + 3 * 1024**3:
        raise RuntimeError('Not enough disk space. Keep at least 3 GB free; remove unused models or recordings.')
