import atexit
import io
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .storage import ROOT, RESOURCE_ROOT, DATA, MODELS, RECORDINGS, LOCK, settings, write_json, list_recordings, get_recording, save_recording, recording_path, disk_info, require_space
from .models import manager, CATALOG
from .pipeline import work, process_recording
from .audio import RATE, spectrogram_png, decode_file

@asynccontextmanager
async def lifespan(app):
    for rec in list_recordings():
        if rec['status'] in ('processing', 'importing'):
            rec.update(status='interrupted', error='The previous run was interrupted. Reprocess the recording or import it again.')
            save_recording(rec)
    yield
    work.cancel_event.set()
    manager.shutdown()

app = FastAPI(title='Nipahut AI Transcriber', docs_url=None, redoc_url=None, lifespan=lifespan)
atexit.register(manager.shutdown)

@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0]
    if host not in ('127.0.0.1', 'localhost', 'testserver'):
        return Response('Local access only', status_code=403)
    origin = request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8765', 'http://localhost:8765', 'http://testserver'):
        return Response('Cross-origin access is disabled', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'"
    return response

@app.exception_handler(FileNotFoundError)
async def missing(request, exc):
    return Response('Not found', status_code=404)

@app.exception_handler(ValueError)
async def invalid(request, exc):
    return Response(str(exc), status_code=400)

def idle():
    if work.snapshot()['state'] == 'running':
        raise HTTPException(409, 'Wait for the active operation or cancel it first.')

class Cleanup(BaseModel):
    denoise: bool = False
    dehiss: bool = False
    hum: Literal['off', '50', '60'] = 'off'
    normalize: bool = False
    strength: float = Field(.35, ge=.05, le=.8)

class Preferences(BaseModel):
    theme: Literal['light', 'dark'] = 'light'
    asr_model: Literal['whisper-small', 'whisper-base', 'whisper-turbo'] = 'whisper-small'
    speaker_model: Literal['diarization', 'diarization-campplus', 'diarization-eres2net'] = 'diarization'
    name_model: Literal['rules', 'qwen-0.6b'] = 'rules'
    language: Literal['auto', 'en', 'filipino', 'taglish', 'cebuano', 'bicolano'] = 'auto'
    detect_names: bool = True
    introduction_seconds: int = Field(90, ge=15, le=600)
    speaker_count: int = Field(0, ge=0, le=20)
    cluster_threshold: float = Field(.5, ge=.1, le=.95)
    cleanup: Cleanup = Field(default_factory=Cleanup)
    diarization_audio: Literal['original', 'cleaned'] = 'original'
    auto_unload: bool = True
    verify_uncertain_speakers: bool = True

@app.get('/api/state')
def state():
    recordings = [{k: r.get(k) for k in ('id', 'title', 'filename', 'duration', 'created_at', 'status')} for r in list_recordings()]
    return {'settings': settings(), 'models': manager.state(), 'job': work.snapshot(), 'recordings': recordings, 'disk': disk_info()}

@app.put('/api/settings')
def update_settings(value: Preferences):
    write_json(DATA / 'settings.json', value.model_dump())
    return settings()

@app.post('/api/models/{mid}/{action}')
def model_action(mid: str, action: Literal['download', 'load', 'unload', 'delete']):
    if mid not in CATALOG or mid == 'rules':
        raise HTTPException(400, 'Choose a downloadable model.')
    idle()
    if action == 'delete' and any(m.get('requires') == mid and m['installed'] for m in manager.state()):
        raise HTTPException(409, 'Remove the alternative speaker models first; they share this segmentation model.')
    def run():
        if action == 'download':
            work.update(stage='download', message='Preparing download…')
            manager.download(mid, lambda p, text: work.update(progress=p, message=text), work.check)
        elif action == 'load':
            work.update(stage='load', message='Loading ' + CATALOG[mid]['label'] + '…')
            manager.load(mid)
        elif action == 'unload':
            work.update(stage='unload', message='Freeing model memory…')
            manager.unload(mid)
        elif action == 'delete':
            manager.unload(mid)
            target = (MODELS / mid).resolve()
            if target.parent != MODELS.resolve():
                raise ValueError('Invalid model directory')
            if target.exists():
                shutil.rmtree(target)
    work.submit('model', run)
    return {'accepted': True}

@app.post('/api/recordings')
def import_audio(file: UploadFile = File(...)):
    idle()
    require_space(512 * 1024**2)
    suffix = Path(file.filename or 'audio.wav').suffix.lower()
    if suffix not in ('.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus', '.aac', '.mp4', '.webm', '.wma'):
        raise HTTPException(400, 'Choose WAV, MP3, M4A, FLAC, OGG, OPUS, AAC, MP4, WEBM or WMA audio.')
    rid = uuid.uuid4().hex
    folder = RECORDINGS / rid
    folder.mkdir()
    original = folder / ('source' + suffix)
    try:
        with original.open('wb') as output:
            size = 0
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > 512 * 1024**2:
                    raise HTTPException(413, 'This version supports files up to 512 MB.')
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, 'The selected audio file is empty.')
        rec = {'id': rid, 'title': Path(file.filename).stem, 'filename': Path(file.filename).name,
               'created_at': datetime.now(timezone.utc).isoformat(), 'duration': 0, 'status': 'importing',
               'segments': [], 'turns': [], 'speakers': [], 'warnings': [], 'cleaned': False}
        save_recording(rec)
        def prepare():
            work.update(stage='prepare', message='Preparing audio and spectrogram…')
            duration = decode_file(original, folder / 'original.wav', work.check, lambda p: work.update(progress=p))
            rec.update(duration=duration, status='ready')
            save_recording(rec)
        work.submit('import', prepare, rid)
        return {'id': rid}
    except Exception:
        # Only remove the fresh, known import directory if no worker has taken it.
        if not (folder / 'recording.json').exists():
            shutil.rmtree(folder)
        raise
    finally:
        file.file.close()

@app.get('/api/recordings/{rid}')
def recording(rid: str):
    return get_recording(rid)

class ParticipantCount(BaseModel):
    count: int = Field(0, ge=0, le=20)

@app.put('/api/recordings/{rid}/participants')
def participant_count(rid: str, value: ParticipantCount):
    idle()
    rec = get_recording(rid)
    rec['expected_speakers'] = value.count
    save_recording(rec)
    return rec

class ProcessOptions(BaseModel):
    mode: Literal['full', 'speakers'] = 'full'

class ClipEdit(BaseModel):
    start: float = Field(ge=0,allow_inf_nan=False)
    end: float = Field(gt=0,allow_inf_nan=False)
    action: Literal['silence','restore']
    speaker_id: str

@app.post('/api/recordings/{rid}/audio-edits')
def edit_audio_clip(rid: str, value: ClipEdit):
    idle()
    rec=get_recording(rid)
    if value.speaker_id not in {s['id'] for s in rec['speakers']} | {'unknown'}:
        raise HTTPException(400,'Speaker not found.')
    from .audio_edits import normalize_silences,restore_range
    selection=normalize_silences([value.model_dump()],rec['duration'])[0]
    per_speaker=dict(rec.get('speaker_silences',{}))
    existing=per_speaker.get(value.speaker_id,[])
    if value.action=='silence':
        owned=[{'start':max(t['start'],selection['start']),'end':min(t['end'],selection['end'])}
            for t in rec['turns'] if t['speaker_id']==value.speaker_id and t['end']>selection['start'] and t['start']<selection['end']]
        if not owned:raise HTTPException(400,'No activity from this speaker is inside the selection.')
        for part in owned:
            if any(t['speaker_id']!=value.speaker_id and min(t['end'],part['end'])>max(t['start'],part['start'])
                   for t in rec['turns']):
                raise HTTPException(409,'This speaker overlaps another voice. Speaker-only muting requires separated tracks; other voices have not been muted.')
        updated=normalize_silences(existing+owned,rec['duration'])
    else:updated=restore_range(existing,selection['start'],selection['end'])
    if len(updated)>1000:raise HTTPException(400,'Too many separate audio edits; restore some ranges first.')
    per_speaker[value.speaker_id]=updated
    rec['speaker_silences']=per_speaker
    rec['silenced_ranges']=normalize_silences([r for ranges in per_speaker.values() for r in ranges],rec['duration'])
    rec['audio_edits_pending']=rec['silenced_ranges']!=rec.get('transcript_silenced_ranges',[])
    save_recording(rec)
    return rec

class VoiceReference(BaseModel):
    id: str = Field(pattern=r'^speaker_[0-9]{2}$')
    name: str = Field(min_length=1, max_length=60)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    confirmed: bool = False
    name_confirmed: bool = False

class VoiceReferences(BaseModel):
    references: list[VoiceReference] = Field(max_length=20)

@app.put('/api/recordings/{rid}/references')
def voice_references(rid: str, value: VoiceReferences):
    idle()
    rec = get_recording(rid)
    refs = [r.model_dump() for r in value.references]
    if len({r['id'] for r in refs}) != len(refs):
        raise HTTPException(400, 'Each reference must have a different speaker ID.')
    if any(not .7 <= r['end']-r['start'] <= 15 or r['end'] > rec['duration'] for r in refs):
        raise HTTPException(400, 'Choose 0.7–15 seconds of clean speech within the recording for each voice.')
    rec['voice_references'] = refs
    save_recording(rec)
    return rec

@app.post('/api/recordings/{rid}/process')
def process(rid: str, options: ProcessOptions | None = None):
    idle()
    rec = get_recording(rid)
    if not (recording_path(rid) / 'original.wav').exists():
        raise HTTPException(400, 'Audio preparation has not completed.')
    opts = settings()
    speakers_only = bool(options and options.mode == 'speakers')
    if speakers_only and rec.get('silenced_ranges',[])!=rec.get('transcript_silenced_ranges',[]):
        raise HTTPException(400,'Audio edits changed. Run full transcription to update the words as well as speakers.')
    expected = rec.get('expected_speakers', opts['speaker_count'])
    if rec.get('voice_references') and expected and len(rec['voice_references']) != expected:
        raise HTTPException(400, 'Provide one clean voice reference per participant, or remove references to use automatic clustering.')
    if speakers_only and not rec.get('segments'):
        raise HTTPException(400, 'Transcribe this recording before updating its speaker labels.')
    needed = [opts['speaker_model']] + ([] if speakers_only else [opts['asr_model']])
    if opts['detect_names'] and opts['name_model'] == 'qwen-0.6b':
        needed.append('qwen-0.6b')
    installed = {m['id'] for m in manager.state() if m['installed']}
    missing = [CATALOG[mid]['label'] for mid in needed if mid not in installed]
    if missing:
        raise HTTPException(400, 'Download these models in Settings first: ' + ', '.join(missing))
    require_space(int(rec['duration'] * RATE * 4))
    work.submit('process', lambda: process_recording(rid, speakers_only=speakers_only), rid)
    return {'accepted': True}

@app.post('/api/jobs/cancel')
def cancel():
    if work.snapshot()['state'] != 'running':
        raise HTTPException(409, 'No operation is running.')
    work.cancel()
    return {'accepted': True}

class SpeakerEdit(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    confirmed: bool = True

@app.patch('/api/recordings/{rid}/speakers/{sid}')
def edit_speaker(rid: str, sid: str, edit: SpeakerEdit):
    idle()
    rec = get_recording(rid)
    speaker = next((s for s in rec['speakers'] if s['id'] == sid), None)
    if speaker is None:
        raise HTTPException(404, 'Speaker not found')
    speaker.update(name=edit.name.strip(), confirmed=edit.confirmed)
    for reference in rec.get('voice_references',[]):
        if reference['id'] == sid:
            reference.update(name=speaker['name'], name_confirmed=edit.confirmed)
    save_recording(rec)
    return rec

class TextEdit(BaseModel):
    text: str = Field(max_length=10000)
    speaker_id: str | None = None

@app.patch('/api/recordings/{rid}/segments/{index}')
def edit_segment(rid: str, index: int, edit: TextEdit):
    idle()
    rec = get_recording(rid)
    if not 0 <= index < len(rec['segments']):
        raise HTTPException(404, 'Transcript segment not found')
    seg = rec['segments'][index]
    if edit.speaker_id is not None:
        valid = {s['id'] for s in rec['speakers']} | {'unknown', 'overlap'}
        if edit.speaker_id not in valid:
            raise HTTPException(400, 'Speaker not found')
        seg['speaker_id'] = edit.speaker_id
        if edit.speaker_id not in ('overlap', 'unknown'):
            seg.update(speaker_ids=[edit.speaker_id], attribution='manually_assigned', overlap=False, identity_review=False)
        elif edit.speaker_id == 'unknown':
            seg.update(speaker_ids=[], attribution='unassigned', overlap=False, identity_review=True)
        else:
            seg.update(overlap=True, attribution='ambiguous_overlap', identity_review=True)
    seg['text'] = edit.text.strip()
    save_recording(rec)
    return rec

@app.delete('/api/recordings/{rid}')
def delete_recording(rid: str):
    idle()
    path = recording_path(rid).resolve()
    if path.parent != RECORDINGS.resolve():
        raise HTTPException(400, 'Invalid recording path')
    shutil.rmtree(path)
    return {'deleted': True}

def audio_path(rid, variant):
    if variant not in ('original', 'cleaned'):
        raise HTTPException(400, 'Invalid audio variant')
    path = recording_path(rid) / (variant + '.wav')
    if not path.exists():
        raise HTTPException(404, 'Audio is not ready.')
    return path

@app.get('/api/recordings/{rid}/audio/{variant}')
def audio_file(rid: str, variant: str):
    return FileResponse(audio_path(rid, variant), media_type='audio/wav')

@app.get('/api/recordings/{rid}/spectrogram')
def spectrum(rid: str, variant: str = 'original', start: float = 0, end: float | None = None, compact: bool = False):
    path = audio_path(rid, variant)
    import hashlib
    key = hashlib.sha256(f'{variant}:{path.stat().st_mtime_ns}:{start}:{end}:{compact}'.encode()).hexdigest()[:24]
    cache = recording_path(rid) / ('spectrum-' + key + '.png')
    if not cache.exists():
        data = spectrogram_png(path, start, end, 380 if compact else 1400, 100 if compact else 270)
        cache.write_bytes(data)
    return FileResponse(cache, media_type='image/png', headers={'Cache-Control': 'private, max-age=86400'})

def timestamp(seconds, srt=False):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02}{"," if srt else "."}{ms:03}'

@app.get('/api/recordings/{rid}/export/{format}')
def export(rid: str, format: Literal['txt', 'srt', 'json', 'rttm', 'pdf']):
    rec = get_recording(rid)
    if rec['status'] != 'complete':
        raise HTTPException(409, 'Finish processing before exporting.')
    names = {s['id']: s['name'] for s in rec['speakers']}
    def label(segment):
        if segment.get('overlap') or segment['speaker_id'] == 'overlap':
            return 'Overlap [' + ' + '.join(names.get(sid, sid) for sid in segment.get('speaker_ids', [])) + '] · mixed audio'
        return names.get(segment['speaker_id'], 'Unknown')
    if format == 'pdf':
        from .pdf_export import transcript_pdf
        return Response(transcript_pdf(rec,label),media_type='application/pdf',
            headers={'Content-Disposition':'attachment; filename="transcript.pdf"'})
    if format == 'json':
        content = json.dumps(rec, ensure_ascii=False, indent=2)
    elif format == 'rttm':
        content = '\n'.join(f'SPEAKER {rid} 1 {t["start"]:.3f} {t["end"]-t["start"]:.3f} <NA> <NA> {t["speaker_id"]} <NA> <NA>' for t in rec['turns']) + '\n'
    elif format == 'txt':
        content = '\n\n'.join(f'[{timestamp(s["start"])[:-4]}] {label(s)}: {s["text"]}' for s in rec['segments'])
    else:
        content = '\n\n'.join(f'{i + 1}\n{timestamp(s["start"], True)} --> {timestamp(s["end"], True)}\n{label(s)}: {s["text"]}' for i, s in enumerate(rec['segments']))
    return Response(content, media_type='application/json' if format == 'json' else 'text/plain; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="transcript.{format}"'})

app.mount('/', StaticFiles(directory=RESOURCE_ROOT / 'static', html=True), name='ui')
