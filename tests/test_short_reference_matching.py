from types import SimpleNamespace
import numpy as np
from app import voice_references


def test_short_name_uses_acoustic_reference_not_wrong_native_majority(monkeypatch):
    class Stream:
        def accept_waveform(self,*,sample_rate,waveform):self.waveform=waveform
        def input_finished(self):pass
    class Extractor:
        def __init__(self,*a,**k):pass
        def create_stream(self):return Stream()
        def is_ready(self,s):return True
        def compute(self,s):return np.array([0.,1.]) if np.mean(s.waveform)>3.5 else np.array([1.,0.])
    monkeypatch.setattr(voice_references.so,'SpeakerEmbeddingExtractor',Extractor)
    monkeypatch.setattr(voice_references.so,'SpeakerEmbeddingExtractorConfig',lambda **kwargs:None)
    audio=np.arange(6*16000,dtype=np.float32)/16000
    refs=[{'id':'a','start':0,'end':2},{'id':'b','start':4,'end':5}]
    turns=[{'start':0,'end':3,'speaker_id':'wrong_merged_cluster'},{'start':4,'end':4.6,'speaker_id':'wrong_merged_cluster'}]
    result,_=voice_references.enroll_and_match(audio,turns,refs,'test')
    assert result[0]['speaker_id']=='a'
    short=next(t for t in result if t['start']==4)
    assert short['speaker_id']=='b' and short['end']==4.6
    assert short['verification']=='short_context_reference'


def test_partial_references_keep_new_voices_and_do_not_reuse_colliding_ids(monkeypatch):
    from app import voice_profiles
    def embed(audio,a,b):return np.eye(3,dtype=np.float32)[int(a)//4]
    monkeypatch.setattr(voice_profiles,'extractor',lambda mid:embed)
    turns=[{'start':i*4.,'end':i*4.+3,'speaker_id':f'speaker_{i:02}'} for i in range(3)]
    refs=[{'id':'speaker_00','start':0,'end':2},{'id':'speaker_01','start':4,'end':6}]
    result,diag=voice_references.match_partial_references(np.zeros(12*16000),turns,refs,'a','b',maximum=24)
    assert result[0]['speaker_id']=='speaker_00'
    assert next(t for t in result if t['start']==4)['speaker_id']=='speaker_01'
    other=next(t for t in result if t['start']==8)
    assert other['speaker_id'] not in ('unknown','speaker_00','speaker_01')
    assert diag['other_voices_retained'] and not diag['human_verified']


def test_continuity_only_fills_short_edge_with_no_conflicting_reference():
    turns=[{'start':0,'end':1,'speaker_id':'candidate'},
           {'start':1,'end':5,'speaker_id':'a','verification':'partial_reference_consensus'}]
    activity=[{'start':0,'end':5,'ids':('native',)}]
    assert voice_references.extend_reference_continuity(turns,activity,{'a','b'})[0]['speaker_id']=='a'
    turns[0].update(speaker_id='b',verification='partial_reference_consensus')
    assert voice_references.extend_reference_continuity(turns,activity,{'a','b'})[0]['speaker_id']=='b'
