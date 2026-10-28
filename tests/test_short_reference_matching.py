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
