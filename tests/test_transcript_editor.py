from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app import server, readability


@pytest.fixture
def editor(monkeypatch):
    rec={'id':'a'*32,'status':'complete','turns':[],
         'speakers':[{'id':'a','name':'Fictional Ana'},{'id':'b','name':'Fictional Ben'}],
         'segments':[{'start':i,'end':i+.8,'speaker_id':'a' if i<3 else 'b','text':text,
                      'words':[{'start':i,'end':i+.8,'word':text}]} for i,text in enumerate(['hello','from','Ana','hello Ben'])]}
    monkeypatch.setattr(server,'idle',lambda:None)
    monkeypatch.setattr(server,'get_recording',lambda rid:rec)
    monkeypatch.setattr(server,'save_recording',lambda value:None)
    def save(**changes):
        group=readability.answer_groups(rec)[0]
        return TestClient(server.app).patch(f"/api/recordings/{rec['id']}/answers/0",json={
            'fingerprint':group['fingerprint'],'text':group['text'],**changes})
    return rec,save


def test_name_and_content_edit_together_preserve_machine_words(editor):
    rec,save=editor;original=deepcopy(rec['segments'])
    response=save(text='Hello from Ana.',speaker_id='a',speaker_name='Fictional Ana Cruz')
    assert response.status_code==200
    assert response.json()['answer_groups'][0]['text']=='Hello from Ana.'
    assert rec['speakers'][0]['name']=='Fictional Ana Cruz' and rec['speakers'][0]['confirmed']
    assert rec['segments']==original and rec['turns']==[]


def test_group_assignment_does_not_swallow_neighbour_or_move_word_timestamps(editor):
    rec,save=editor;original=deepcopy(rec['segments'])
    response=save(text='Corrected answer.',speaker_id='b',speaker_name='Fictional Ben')
    assert response.status_code==200
    groups=response.json()['answer_groups']
    assert groups[0]['indices']==[0,1,2] and groups[1]['indices']==[3]
    assert groups[0]['speaker_id']=='b' and groups[0]['text']=='Corrected answer.'
    for old,new in zip(original,rec['segments']):
        assert (old['start'],old['end'],old['words'],old['text'])==(new['start'],new['end'],new['words'],new['text'])
    assert rec['segments'][0]['original_speaker_assignment']['speaker_id']=='a'
    assert rec['segments'][3]==original[3]
    response=save(text='Still corrected.',speaker_id='unknown')
    assert response.json()['answer_groups'][0]['indices']==[0,1,2]
    assert response.json()['answer_groups'][0]['speaker_id']=='unknown'
    assert rec['segments'][0]['original_speaker_assignment']['speaker_id']=='a'


def test_new_person_can_be_added_to_correct_an_unassigned_answer(editor):
    rec,save=editor
    response=save(speaker_id='__new__',speaker_name='Fictional Clara',text='Clara speaking.')
    assert response.status_code==200
    group=response.json()['answer_groups'][0]
    person=next(s for s in rec['speakers'] if s['id']==group['speaker_id'])
    assert person['name']=='Fictional Clara' and person['confirmed'] and person['manually_created']
    assert group['indices']==[0,1,2]


def test_manual_overlap_can_identify_both_people(editor):
    rec,save=editor
    response=save(speaker_id='overlap',speaker_ids=['a','b'],text='Two voices together.')
    assert response.status_code==200
    group=response.json()['answer_groups'][0]
    assert group['speaker_id']=='overlap' and group['speaker_ids']==['a','b']
    assert group['overlap'] and group['indices']==[0,1,2]
    assert all(s['original_speaker_assignment']['speaker_id']=='a' for s in rec['segments'][:3])


@pytest.mark.parametrize('changes',[
    {'speaker_id':'b','speaker_name':'   '},
    {'speaker_id':'missing','speaker_name':'Changed'},
    {'speaker_id':'__new__','speaker_name':'Fictional Ana'},
    {'speaker_id':'overlap','speaker_ids':['a']},
    {'speaker_id':'overlap','speaker_ids':['a','a']},
    {'speaker_id':'unknown','speaker_name':'Changed'},
    {'text':'   ','speaker_id':'b','speaker_name':'Changed'},
])
def test_invalid_edits_do_not_partially_rename_or_modify_source(editor,changes):
    rec,save=editor;original=deepcopy(rec)
    assert save(**changes).status_code==400
    assert rec==original


def test_stale_source_rejects_rename_as_well_as_text(editor):
    rec,save=editor;original=deepcopy(rec)
    assert save(fingerprint='0'*64,speaker_id='b',speaker_name='Changed',text='Changed').status_code==409
    assert rec==original


def test_text_only_save_does_not_confirm_an_unchanged_machine_name(editor):
    rec,save=editor
    rec['speakers'][0].update(name='Speaker 01',confirmed=False,suggested=False)
    response=save(text='Corrected words.',speaker_id='a',speaker_name='Speaker 01')
    assert response.status_code==200
    assert not rec['speakers'][0]['confirmed']
