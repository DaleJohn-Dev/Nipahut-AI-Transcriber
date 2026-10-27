import numpy as np
from fastapi.testclient import TestClient
from app import server
from app.audio_edits import apply_silences,normalize_silences,restore_range

def setup_record(monkeypatch,turns):
    rec={'duration':10,'status':'complete','speakers':[{'id':'a'},{'id':'b'}],'turns':turns}
    monkeypatch.setattr(server,'idle',lambda:None)
    monkeypatch.setattr(server,'get_recording',lambda _:rec)
    monkeypatch.setattr(server,'save_recording',lambda _:None)
    return rec,TestClient(server.app)

def test_speaker_edit_does_not_mute_other_turns_between_selected_parts(monkeypatch):
    rec,c=setup_record(monkeypatch,[{'start':0,'end':2,'speaker_id':'a'},{'start':2,'end':4,'speaker_id':'b'},{'start':4,'end':6,'speaker_id':'a'}])
    r=c.post('/api/recordings/'+'0'*32+'/audio-edits',json={'start':0,'end':6,'speaker_id':'a','action':'silence'})
    assert r.status_code==200
    assert rec['silenced_ranges']==[{'start':0,'end':2},{'start':4,'end':6}]
    assert rec['audio_edits_pending']

def test_overlapping_voice_mute_is_refused_without_separated_tracks(monkeypatch):
    rec,c=setup_record(monkeypatch,[{'start':0,'end':5,'speaker_id':'a'},{'start':2,'end':3,'speaker_id':'b'}])
    r=c.post('/api/recordings/'+'0'*32+'/audio-edits',json={'start':1,'end':4,'speaker_id':'a','action':'silence'})
    assert r.status_code==409
    assert 'separated tracks' in r.json()['detail']
    assert 'silenced_ranges' not in rec

def test_silence_copy_keeps_samples_duration_and_adjacent_voices():
    audio=np.ones(16000,dtype=np.float32)
    result=apply_silences(audio,[{'start':.2,'end':.6}])
    assert np.array_equal(audio,np.ones(16000,dtype=np.float32))
    assert result.shape==audio.shape
    assert np.array_equal(result[:3200],audio[:3200])
    assert np.array_equal(result[9600:],audio[9600:])
    assert np.max(np.abs(result[3280:9520]))==0
    assert restore_range([{'start':1,'end':5}],2,3)==[{'start':1,'end':2},{'start':3,'end':5}]
    assert normalize_silences([{'start':1,'end':3},{'start':2,'end':4}],10)==[{'start':1,'end':4}]
