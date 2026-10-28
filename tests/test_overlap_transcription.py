from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from app import overlap_transcription as overlap,readability


def test_context_windows_batch_nearby_ranges_without_processing_solo_recording():
    groups=[{'start':20,'end':21},{'start':21,'end':22},{'start':100,'end':101}]
    batches=overlap.windows(groups,200)
    assert [(b['start'],b['end']) for b in batches]==[(18.5,23.5),(98.5,102.5)]
    assert len(batches[0]['groups'])==2
    assert overlap.windows([{'start':0,'end':25}],100)==[]
    assert all(b['end']-b['start']<=20 for b in batches)


def test_matching_rejects_same_identity_weak_scores_and_ambiguous_sources():
    centers={'a':np.array([1.,0]),'b':np.array([0.,1])}
    assert overlap.match_sources([np.array([1.,0]),np.array([0.,1])],centers)==['a','b']
    assert overlap.match_sources([np.array([1.,0]),np.array([1.,0])],centers)==[None,None]
    assert overlap.match_sources([np.array([.5,.5]),None],centers)==[None,None]
    assert overlap.match_sources([np.array([.2,0]),None],centers)==[None,None]


def test_recovery_really_transcribes_each_source_and_keeps_common_interval(monkeypatch):
    from app import models,separation,audio,voice_profiles
    group_rec={'duration':6,'speakers':[{'id':'a'},{'id':'b'}],'segments':[
        {'start':2,'end':3,'speaker_id':'overlap','speaker_ids':['a','b'],'overlap':True,'text':'Mixed.'}]}
    calls=[]
    class ASR:
        def transcribe(self,sample,**kwargs):
            calls.append(sample.copy());word=' Ana.' if len(calls)==1 else ' Ben.'
            return iter([SimpleNamespace(avg_logprob=-.2,no_speech_prob=.1,words=[SimpleNamespace(start=1.6,end=2.2,word=word)])]),None
    manager=SimpleNamespace(loaded={'sepformer-whamr':object(),'whisper-small':ASR()},load=lambda _:None,unload=lambda _:None)
    monkeypatch.setattr(models,'manager',manager)
    monkeypatch.setattr(audio,'read_audio',lambda _:np.zeros(6*16000,dtype=np.float32))
    monkeypatch.setattr(separation,'source_signature',lambda *_:'signature')
    t=np.arange(4*16000)/16000
    sources=np.stack([np.sin(t*100),np.cos(t*120)],axis=1).astype('float32')
    monkeypatch.setattr(separation,'separate_clip',lambda *_:sources)
    vectors=iter([np.array([1.,0]),np.array([0.,1])])
    monkeypatch.setattr(voice_profiles,'extractor',lambda _:lambda *_:next(vectors))
    monkeypatch.setattr(overlap,'solo_centers',lambda *_:{'a':np.array([1.,0]),'b':np.array([0.,1])})
    result=overlap.run_inference(Path('.'),group_rec,{'speaker_model':'test','asr_model':'whisper-small','language':'filipino'})
    assert len(calls)==2 and not np.array_equal(calls[0],calls[1])
    assert result[0]['accepted'] and [s['text'] for s in result[0]['sources']]==['Ana.','Ben.']
    assert result[0]['start']==2 and result[0]['end']==3
    assert result[0]['sources'][0]['words'][0]['start']==2.1


def test_unaccepted_stale_and_manually_corrected_outputs_do_not_replace_words():
    rec={'speakers':[{'id':'a'},{'id':'b'}],'segments':[
        {'start':2,'end':3,'speaker_id':'overlap','speaker_ids':['a','b'],'overlap':True,'text':'Mixed.'}]}
    group=readability.answer_groups(rec)[0]
    candidate={'fingerprint':group['fingerprint'],'accepted':False,'sources':[{'speaker_id':'a','text':'Separated.'}]}
    rec['overlap_transcripts']=[candidate]
    assert not readability.answer_groups(rec)[0].get('overlap_sources')
    candidate['accepted']=True
    assert readability.answer_groups(rec)[0]['overlap_sources'][0]['text']=='Separated.'
    changed=deepcopy(rec);changed['silenced_ranges']=[{'start':2,'end':2.5}]
    assert not readability.answer_groups(changed)[0].get('overlap_sources')
    rec['answer_edits']={'0':{'fingerprint':group['fingerprint'],'text':'Human correction.'}}
    rows=readability.transcript_rows(readability.answer_groups(rec),rec['speakers'])
    assert len(rows)==1 and rows[0]['text']=='Human correction.'
