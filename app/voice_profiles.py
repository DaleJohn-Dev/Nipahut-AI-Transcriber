"""Explicitly enrolled local speaker embeddings; never auto-update from guesses."""
import hashlib
import uuid
import re
from datetime import datetime, timezone
import numpy as np
import soundfile as sf
from . import storage
from .audio import RATE
from .voice_classifier import unit


_model_keys = {}


def model_key(model_id):
    path = storage.MODELS/model_id/'embedding.onnx'
    stat = path.stat()
    signature = (stat.st_mtime_ns,stat.st_size)
    cached = _model_keys.get(path)
    if cached and cached[0] == signature:
        return cached[1]
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    _model_keys[path] = (signature,model_id+':'+digest)
    return model_id + ':' + digest


def library():
    return storage.read_json(storage.DATA/'voice-profiles.json', {'profiles': []})


def available(model_id):
    key = model_key(model_id)
    return [p for p in library()['profiles'] if p['model_key'] == key]


def summaries():
    return [{k:p[k] for k in ('id','name','model_id','samples','updated_at')} for p in library()['profiles']]


def save(name, model_id, vector):
    name = name.strip()
    vector = unit(vector)
    if not name or len(name)>60 or vector is None:
        raise ValueError('A name and usable clean voice sample are required.')
    if re.fullmatch(r'(?:speaker[\s_]*\d+|unknown|unresolved.*)',name,re.I):
        raise ValueError('Enter a confirmed person name or unique label instead of the automatic speaker number.')
    key = model_key(model_id)
    with storage.LOCK:
        data = library()
        profile = next((p for p in data['profiles'] if p['model_key']==key and p['name'].casefold()==name.casefold()), None)
        if profile is None:
            profile = {'id':uuid.uuid4().hex,'name':name,'model_id':model_id,'model_key':key,'vectors':[],'samples':0}
            data['profiles'].append(profile)
        profile['vectors'] = (profile['vectors']+[vector.tolist()])[-5:]
        profile['samples'] = len(profile['vectors'])
        profile['updated_at'] = datetime.now(timezone.utc).isoformat()
        storage.write_json(storage.DATA/'voice-profiles.json', data)
    return summaries()


def delete(pid):
    with storage.LOCK:
        data = library()
        data['profiles'] = [p for p in data['profiles'] if p['id'] != pid]
        storage.write_json(storage.DATA/'voice-profiles.json', data)


def extractor(model_id):
    import sherpa_onnx as so
    model = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(
        model=str(storage.MODELS/model_id/'embedding.onnx'), num_threads=2, provider='cpu'))
    def embed(audio, start, end):
        samples = np.ascontiguousarray(audio[int(start*RATE):int(end*RATE)], dtype=np.float32)
        if len(samples)<int(.7*RATE) or not np.isfinite(samples).all() or np.sqrt(np.mean(samples*samples))<1e-4:
            return None
        stream = model.create_stream()
        stream.accept_waveform(sample_rate=RATE, waveform=samples)
        stream.input_finished()
        return unit(model.compute(stream)) if model.is_ready(stream) else None
    return embed


def enroll(path, name, model_id, start, end):
    if not 2 <= end-start <= 8:
        raise ValueError('Choose 2–8 seconds of clean speech by one person.')
    with sf.SoundFile(str(path)) as source:
        if source.samplerate != RATE or start < 0 or end > len(source)/RATE:
            raise ValueError('Choose a voice sample within this recording.')
        source.seek(int(start*RATE))
        audio = source.read(int((end-start)*RATE), dtype='float32', always_2d=True).mean(axis=1)
    vector = extractor(model_id)(audio, 0, len(audio)/RATE)
    return save(name, model_id, vector)
