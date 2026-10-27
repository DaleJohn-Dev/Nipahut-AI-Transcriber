"""Optional two-source SepFormer ONNX review; no inferred identity is asserted."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .audio import RATE

MODEL_ID='sepformer-whamr'
MODEL_REPO='tonythethompson/SepFormer-WhamR16k-ONNX'
MODEL_SHA256='d1e5ed49b7cc09e2c5946ce710fec33692b13a69c9c40441b0b14120cb649553'
MAX_CLIP_SECONDS=20

def load_separator(folder):
    import onnxruntime as ort
    path=Path(folder)/'model.onnx'
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=MODEL_SHA256:
            raise RuntimeError('The separation model checksum does not match. Remove it and download again.')
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    options.enable_cpu_mem_arena=False
    session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
    if len(session.get_inputs())!=1:raise RuntimeError('Unexpected separation model inputs.')
    return session

def separate_clip(session,audio,check=lambda:None):
    samples=np.asarray(audio,dtype=np.float32).reshape(-1)
    if not RATE*.5<=len(samples)<=RATE*MAX_CLIP_SECONDS:
        raise ValueError('Select between 0.5 and 20 seconds for experimental separation.')
    check()
    model_input=np.ascontiguousarray(samples[None,:],dtype=np.float32)
    # The encoder/decoder stride needs padding at arbitrary selection boundaries.
    model_input=np.pad(model_input,((0,0),(0,(-model_input.shape[1])%8)))
    sources=session.run(None,{session.get_inputs()[0].name:model_input})
    check()
    if len(sources)!=2 or any(np.asarray(source).shape!=(model_input.shape[1],) for source in sources):
        raise RuntimeError('The model returned invalid two-source audio.')
    restored=np.stack(sources,axis=1)[:len(samples)]
    if not np.isfinite(restored).all():raise RuntimeError('The model returned non-finite audio.')
    # One shared scale retains the relative levels of the two outputs.
    peak=float(np.max(np.abs(restored)))
    if peak>1:restored/=peak
    return np.ascontiguousarray(restored,dtype=np.float32)

def selection_speakers(recording,start,end):
    if not np.isfinite([start,end]).all() or start<0 or end>recording['duration'] or not .5<=end-start<=MAX_CLIP_SECONDS:
        raise ValueError('Select between 0.5 and 20 seconds inside the recording.')
    ids={t['speaker_id'] for t in recording.get('turns',[]) if min(t['end'],end)>max(t['start'],start)}
    from .diarization import overlap_regions
    overlaps=recording.get('overlap_regions')
    if overlaps is None:overlaps=overlap_regions(recording.get('turns',[]))
    if not any(min(r['end'],end)>max(r['start'],start) for r in overlaps):
        raise ValueError('Select a detected overlapping section. Solo speech is kept unchanged.')
    if len(ids)>2:raise ValueError('This selection contains more than two speaker labels. Select a shorter two-voice section.')
    if len(ids)<2:raise ValueError('Select a section containing two detected voices.')
    return sorted(ids)

def source_signature(folder,recording):
    source=Path(folder)/'original.wav';info=source.stat()
    value=[info.st_size,info.st_mtime_ns,recording.get('silenced_ranges',[])]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
