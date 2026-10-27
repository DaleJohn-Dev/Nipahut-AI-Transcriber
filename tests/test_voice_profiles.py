import numpy as np
import pytest
from app import storage, voice_profiles, server
from fastapi.testclient import TestClient


def prepare(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    monkeypatch.setattr(voice_profiles,'model_key',lambda mid:mid+':test-revision')


def test_library_persists_reviewed_vectors_without_recording_copies(tmp_path,monkeypatch):
    prepare(tmp_path,monkeypatch)
    for i in range(7):voice_profiles.save('Fictional Ana','diarization',np.array([1,.01*i]))
    summary=voice_profiles.summaries()[0]
    assert summary['name']=='Fictional Ana' and summary['samples']==5
    assert 'vectors' not in summary and 'model_key' not in summary
    assert [p.name for p in tmp_path.iterdir()]==['voice-profiles.json']
    assert len(voice_profiles.available('diarization'))==1
    assert voice_profiles.available('diarization-campplus')==[]
    monkeypatch.setattr(voice_profiles,'model_key',lambda mid:mid+':new-revision')
    assert voice_profiles.available('diarization')==[]
    voice_profiles.delete(summary['id'])
    assert voice_profiles.summaries()==[]


def test_enrollment_requires_review_and_rejects_mixed_voice(tmp_path,monkeypatch):
    prepare(tmp_path,monkeypatch)
    monkeypatch.setattr(server,'idle',lambda:None)
    monkeypatch.setattr(server,'get_recording',lambda rid:{'overlap_regions':[{'start':2,'end':4}]})
    monkeypatch.setattr(voice_profiles,'enroll',lambda *args: (_ for _ in ()).throw(AssertionError('Must reject before embedding')))
    client=TestClient(server.app)
    url='/api/recordings/'+'a'*32+'/voice-profile'
    assert client.post(url,json={'name':'Fictional Ana','start':0,'end':3}).status_code==400
    assert client.post(url,json={'name':'Fictional Ana','start':0,'end':3,'reviewed':True}).status_code==400


def test_moderate_cleanup_and_local_matching_are_defaults():
    prefs=server.Preferences()
    assert prefs.cleanup.denoise and prefs.cleanup.strength==.2
    assert not prefs.cleanup.dehiss and not prefs.cleanup.normalize
    assert prefs.use_voice_profiles and prefs.diarization_audio=='cleaned'
    assert prefs.use_voice_classifier


def test_automatic_number_cannot_be_enrolled_as_a_person(tmp_path,monkeypatch):
    prepare(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='confirmed person'):
        voice_profiles.save('Speaker 712','diarization',[1,0])
    assert not (tmp_path/'voice-profiles.json').exists()


def test_actual_model_change_invalidates_profile_key(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'MODELS',tmp_path)
    folder=tmp_path/'diarization';folder.mkdir()
    (folder/'embedding.onnx').write_bytes(b'fictional-model-a')
    before=voice_profiles.model_key('diarization')
    (folder/'embedding.onnx').write_bytes(b'fictional-model-b-updated')
    assert voice_profiles.model_key('diarization')!=before
