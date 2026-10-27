from copy import deepcopy
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app import server, readability
from app.models import CATALOG,ModelManager


def fixture_record():
    segments=[{'start':0,'end':1,'speaker_id':'a','text':'ako'}, {'start':1.1,'end':2,'speaker_id':'a','text':'po si Ana'}, {'start':2.1,'end':3,'speaker_id':'a','text':'kumusta'}, {'start':3.1,'end':4,'speaker_id':'b','text':'mabuti'}]
    return {'id':'a'*32,'status':'complete','segments':segments,'turns':[],'speakers':[{'id':'a','name':'Ana'},{'id':'b','name':'Ben'}]}


def test_answer_grouping_preserves_every_fragment_and_word_timestamp():
    rec=fixture_record();rec['segments'][0]['words']=[{'start':0,'end':1,'word':'ako'}];original=deepcopy(rec)
    groups=readability.answer_groups(rec)
    assert [g['text'] for g in groups]==['ako po si Ana kumusta','mabuti']
    assert groups[0]['indices']==[0,1,2] and groups[0]['start']==0 and groups[0]['end']==3
    assert groups[0]['parts'][0]['words']==rec['segments'][0]['words']
    assert rec==original


def test_groups_stop_at_other_speaker_overlap_pause_and_unknown():
    for field,value in [('turns',[{'start':1.01,'end':1.09,'speaker_id':'b'}]),('overlap_regions',[{'start':.9,'end':1.2}])]:
        rec=fixture_record();rec[field]=value
        assert readability.answer_groups(rec)[0]['indices']==[0]
    rec=fixture_record();rec['segments'][1]['start']=2.6;rec['segments'][1]['end']=3
    assert readability.answer_groups(rec)[0]['indices']==[0]
    rec=fixture_record();rec['segments'][0]['speaker_id']=rec['segments'][1]['speaker_id']='unknown'
    assert readability.answer_groups(rec)[0]['indices']==[0]
    rec=fixture_record();rec['segments'][1]['overlap']=True
    assert readability.answer_groups(rec)[0]['indices']==[0]


def test_answer_edit_is_non_destructive_and_stale_edit_is_rejected(monkeypatch):
    rec=fixture_record();original=deepcopy(rec['segments']);monkeypatch.setattr(server,'idle',lambda:None)
    monkeypatch.setattr(server,'get_recording',lambda _:rec);monkeypatch.setattr(server,'save_recording',lambda _:None)
    group=readability.answer_groups(rec)[0];client=TestClient(server.app)
    body={'fingerprint':group['fingerprint'],'text':'Ako po si Ana. Kumusta?'}
    response=client.patch(f"/api/recordings/{rec['id']}/answers/0",json=body)
    assert response.status_code==200 and response.json()['answer_groups'][0]['text']==body['text']
    assert rec['segments']==original
    rec['segments'][1]['text']='corrected audio words'
    assert readability.answer_groups(rec)[0]['text']!=body['text']
    assert client.patch(f"/api/recordings/{rec['id']}/answers/0",json=body).status_code==409


def test_gemma_punctuation_rejects_invented_or_reordered_words(monkeypatch):
    def result(text):return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'choices':[{'message':{'content':text}}]})
    monkeypatch.setattr(readability.httpx,'post',lambda *a,**k:result('Ako po si Ana. Kumusta?'))
    assert readability.punctuation_suggestion('ako po si Ana kumusta')=='Ako po si Ana. Kumusta?'
    for text in ['Ako si Maria. Kumusta?','Kumusta ako po si Ana?','']:
        monkeypatch.setattr(readability.httpx,'post',lambda *a,**k:result(text))
        with pytest.raises(ValueError):readability.punctuation_suggestion('ako po si Ana kumusta')


def test_gemma_is_additive_and_unloading_does_not_stop_qwen():
    assert {'whisper-small','whisper-base','whisper-turbo','qwen-0.6b','gemma-4-e2b'}.issubset(CATALOG)
    manager=ModelManager();events=[]
    manager.loaded={'qwen-0.6b':True,'gemma-4-e2b':True};manager.llama=object()
    manager.gemma=SimpleNamespace(terminate=lambda:events.append('stop'),wait=lambda _:None)
    manager.gemma_log=SimpleNamespace(close=lambda:events.append('close'))
    manager.unload('gemma-4-e2b')
    assert events==['stop','close'] and manager.loaded=={'qwen-0.6b':True} and manager.llama is not None
