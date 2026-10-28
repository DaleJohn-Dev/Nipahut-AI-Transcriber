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
    'cleanup': {'denoise': True, 'dehiss': False, 'hum': 'off', 'normalize': False, 'strength': 0.2},
    'diarization_audio': 'cleaned', 'auto_unload': True,
    'verify_uncertain_speakers': True,
    'use_voice_profiles': True,
    'use_voice_classifier': True,
    'transcribe_overlaps': False,
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

_record_index = {}


def list_recordings():
    records = [read_json(p) for p in RECORDINGS.glob('*/recording.json')]
    return sorted([r for r in records if r], key=lambda r: r['created_at'], reverse=True)


def list_recording_summaries():
    # Atomic saves replace the file: reuse parsed metadata until its identity changes.
    records = []
    with LOCK:
        paths = set(RECORDINGS.glob('*/recording.json'))
        for stale in _record_index.keys() - paths:
            del _record_index[stale]
        for path in paths:
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
                cached = _record_index.get(path)
                if cached is None or cached[0] != signature:
                    value = read_json(path)
                    summary = {k: value.get(k) for k in ('id', 'title', 'filename', 'duration', 'created_at', 'status')} if value else None
                    cached = (signature, summary)
                    _record_index[path] = cached
                records.append(cached[1])
            except FileNotFoundError:
                continue
    return sorted([r for r in records if r], key=lambda r: r['created_at'], reverse=True)

_size_cache = {}
_size_lock = threading.Lock()


def directory_bytes(path):
    # Inventory is advisory; free-space safety checks still query the drive live.
    path = Path(path)
    with _size_lock:
        cached = _size_cache.get(path)
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        total = _directory_bytes(path)
        _size_cache[path] = (time.monotonic(), total)
        return total


def _directory_bytes(path):
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
