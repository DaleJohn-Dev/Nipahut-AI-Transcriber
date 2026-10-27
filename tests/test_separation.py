from types import SimpleNamespace
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from app import server
from app.separation import MODEL_ID,MAX_CLIP_SECONDS,separate_clip,selection_speakers,source_signature

class FakeSeparator:
    def get_inputs(self):return [SimpleNamespace(name='mix')]
    def run(self,_,inputs):
        samples=inputs['mix'][0]
        return [samples*.6,samples*.4]

def test_arbitrary_clip_length_preserves_original_timebase():
    source=np.ones(16001,dtype=np.float32)*.1
    result=separate_clip(FakeSeparator(),source)
    assert result.shape==(len(source),2)
    assert np.allclose(result.sum(axis=1),source)
    assert np.all(source==np.float32(.1))
    checks=[];separate_clip(FakeSeparator(),source,lambda:checks.append(True));assert len(checks)==2

def test_invalid_output_and_clip_size_are_rejected():
    with pytest.raises(ValueError):separate_clip(FakeSeparator(),np.zeros(1600))
    with pytest.raises(ValueError):separate_clip(FakeSeparator(),np.zeros(16000*(MAX_CLIP_SECONDS+1)))
    class Invalid(FakeSeparator):
        def run(self,*args):return [np.full(16000,np.nan),np.zeros(16000)]
    with pytest.raises(RuntimeError):separate_clip(Invalid(),np.zeros(16000))

def test_only_detected_short_two_speaker_overlaps_are_allowed():
    rec={'duration':30,'turns':[{'start':0,'end':10,'speaker_id':'a'},{'start':3,'end':6,'speaker_id':'b'}]}
    assert selection_speakers(rec,3,6)==['a','b']
    for start,end in [(0,2),(0,21),(float('nan'),4),(-1,4),(29,31)]:
        with pytest.raises(ValueError):selection_speakers(rec,start,end)
    rec['turns'].append({'start':4,'end':5,'speaker_id':'c'})
    with pytest.raises(ValueError):selection_speakers(rec,3,6)

def setup_record(monkeypatch,tmp_path):
    rid='a'*32;folder=tmp_path/rid;folder.mkdir();sf.write(folder/'original.wav',np.sin(np.arange(160000)*.1)*.1,16000)
    rec={'id':rid,'status':'complete','duration':10,'segments':[{'text':'Original text'}],'speakers':[{'id':'a','name':'Alice'},{'id':'b','name':'Ben'}],'turns':[{'start':0,'end':8,'speaker_id':'a'},{'start':3,'end':6,'speaker_id':'b'}]}
    models=tmp_path/'models';(models/MODEL_ID).mkdir(parents=True);(models/MODEL_ID/'manifest.json').write_text('{}')
    monkeypatch.setattr(server,'MODELS',models);monkeypatch.setattr(server,'idle',lambda:None)
    monkeypatch.setattr(server,'get_recording',lambda _:rec);monkeypatch.setattr(server,'recording_path',lambda _:folder);monkeypatch.setattr(server,'save_recording',lambda _:None)
    monkeypatch.setattr(server,'require_space',lambda _:None)
    monkeypatch.setattr(server.work,'submit',lambda kind,fn,rid:fn());monkeypatch.setattr(server.work,'check',lambda:None)
    monkeypatch.setattr(server.manager,'loaded',{MODEL_ID:FakeSeparator()});monkeypatch.setattr(server.manager,'load',lambda _:None);monkeypatch.setattr(server.manager,'unload',lambda _:None)
    return rec,folder,TestClient(server.app),rid

def test_preview_needs_confirmation_and_keeps_original(monkeypatch,tmp_path):
    rec,folder,client,rid=setup_record(monkeypatch,tmp_path);original=(folder/'original.wav').read_bytes()
    response=client.post(f'/api/recordings/{rid}/separations',json={'start':3,'end':5});assert response.status_code==200
    cid=response.json()['id'];clip=rec['separations'][0];assert not clip['confirmed'] and clip['speakers']==[]
    assert rec['status']=='complete' and rec['segments']==[{'text':'Original text'}]
    assert (folder/'original.wav').read_bytes()==original
    assert client.get(f'/api/recordings/{rid}/separations/{cid}/audio/0').status_code==200
    assert client.patch(f'/api/recordings/{rid}/separations/{cid}',json={'speakers':['a','a']}).status_code==400
    assert client.patch(f'/api/recordings/{rid}/separations/{cid}',json={'speakers':['a','b']}).status_code==200
    assert clip['confirmed']
    cached=client.post(f'/api/recordings/{rid}/separations',json={'start':3,'end':5});assert cached.json()['cached']
    assert len(rec['separations'])==1
    rec['silenced_ranges']=[{'start':1,'end':2}]
    assert client.get(f'/api/recordings/{rid}/separations/{cid}/audio/0').status_code==409
    assert client.patch(f'/api/recordings/{rid}/separations/{cid}',json={'speakers':['a','b']}).status_code==409
    assert client.delete(f'/api/recordings/{rid}/separations/{cid}').status_code==200
    assert not (folder/'separations'/cid).exists() and (folder/'original.wav').read_bytes()==original

def test_reject_solo_missing_model_and_bad_source_index(monkeypatch,tmp_path):
    rec,folder,client,rid=setup_record(monkeypatch,tmp_path)
    assert client.post(f'/api/recordings/{rid}/separations',json={'start':0,'end':2}).status_code==400
    assert client.get(f'/api/recordings/{rid}/separations/not-valid/audio/0').status_code==400
    (server.MODELS/MODEL_ID/'manifest.json').unlink()
    assert client.post(f'/api/recordings/{rid}/separations',json={'start':3,'end':5}).status_code==400
