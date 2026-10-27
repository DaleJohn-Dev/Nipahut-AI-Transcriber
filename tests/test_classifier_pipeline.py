from copy import deepcopy
import numpy as np
import pytest
from app import pipeline, storage, diarization_worker


def test_classified_identities_stay_bounded_and_unknown_is_not_a_person(tmp_path,monkeypatch):
    rec={'id':'a'*32,'duration':8,'warnings':[],'voice_references':[]}
    opts={**storage.DEFAULTS,'auto_unload':False,'detect_names':False}
    result={'turns':[{'start':0,'end':4,'speaker_id':'profile_fictional','identity_review':True},
                     {'start':4,'end':8,'speaker_id':'unknown','identity_review':True}],
            'classification':{'method':'bounded_global_voice_embeddings','profile_names':{'profile_fictional':'Fictional Ana'}}}
    monkeypatch.setattr(diarization_worker,'run_native_diarization',lambda *a,**k:result)
    monkeypatch.setattr(pipeline,'save_recording',lambda r:None)
    monkeypatch.setattr(pipeline.work,'check',lambda:None)
    pipeline.finish_diarization(rec['id'],rec,opts,tmp_path,np.zeros(1),np.zeros(1),[],
                                lambda mid:None,lambda *a:None,set())
    assert len(rec['speakers'])==1
    assert rec['speakers'][0]['name']=='Fictional Ana'
    assert rec['speakers'][0]['profile_match'] and not rec['speakers'][0]['confirmed']
    assert rec['diarization_diagnostics']['detected_speakers']==1
    assert rec['turns'][-1]['speaker_id']=='unknown'


def test_failed_reanalysis_restores_reviewed_result(tmp_path,monkeypatch):
    original={'id':'a'*32,'status':'complete','cleaned':False,'segments':[{'text':'Reviewed answer'}],
              'speakers':[{'id':'a','name':'Fictional Ana','confirmed':True}],'turns':[],
              'answer_edits':{'0':{'text':'Reviewed correction'}},'separations':[]}
    current=deepcopy(original)
    saved=[]
    monkeypatch.setattr(pipeline,'get_recording',lambda rid:current)
    monkeypatch.setattr(pipeline,'recording_path',lambda rid:tmp_path)
    monkeypatch.setattr(pipeline,'settings',lambda:deepcopy(storage.DEFAULTS))
    monkeypatch.setattr(pipeline,'save_recording',lambda rec:saved.append(deepcopy(rec)))
    monkeypatch.setattr(pipeline.work,'check',lambda:None)
    monkeypatch.setattr(pipeline,'read_audio',lambda path: (_ for _ in ()).throw(RuntimeError('Synthetic failure')))
    with pytest.raises(RuntimeError,match='Synthetic failure'):
        pipeline.process_recording(original['id'],speakers_only=True)
    assert saved[-1]==original
