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
    assert rec['speakers'][0]['name']=='Fictional Ana'
    group=response.json()['answer_groups'][0]
    assert next(p for p in rec['speakers'] if p['id']==group['speaker_id'])['name']=='Fictional Ana Cruz'
    assert rec['segments'][3]==original[3] and rec['turns']==[]
    assert all(s['words']==old['words'] and s['text']==old['text'] for s,old in zip(rec['segments'],original))


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
    {'speaker_id':'overlap','speaker_ids':['a']},
    {'speaker_id':'overlap','speaker_ids':['a','a']},
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


def test_overlap_annotations_keep_same_timestamps_and_mixed_reference_once(editor):
    rec,save=editor
    response=save(speaker_id='overlap',speaker_ids=['a','b'],text='Mixed reference.',speaker_texts={'a':'Hello, Ben.','b':'Hi, Ana.'})
    assert response.status_code==200
    group=response.json()['answer_groups'][0]
    rows=readability.transcript_rows([group],rec['speakers'])
    assert len(rows)==2
    assert [r['text'] for r in rows]==['Hello, Ben.','Hi, Ana.']
    assert all((r['start'],r['end'])==(group['start'],group['end']) for r in rows)
    assert [r['speaker_id'] for r in rows]==['a','b']
    # A normal subsequent save retains reviewed per-speaker words.
    assert save(text='Updated shared reference.').json()['answer_groups'][0]['speaker_texts']=={'a':'Hello, Ben.','b':'Hi, Ana.'}
    txt=TestClient(server.app).get(f"/api/recordings/{rec['id']}/export/txt").text
    assert txt.count('Hello, Ben.')==1 and 'Fictional Ana [simultaneous]' in txt
    srt=TestClient(server.app).get(f"/api/recordings/{rec['id']}/export/srt").text
    assert srt.count('00:00:00,000 --> 00:00:02,800')==2


def test_unseparated_overlap_does_not_duplicate_mixed_words(editor):
    rec,save=editor
    group=save(speaker_id='overlap',speaker_ids=['a','b'],text='Mixed words.').json()['answer_groups'][0]
    rows=readability.transcript_rows([group],rec['speakers'])
    assert sum(r['text']=='Mixed words.' for r in rows)==1
    assert len(rows)==1 and not rows[0].get('words_pending')
    assert len(readability.transcript_rows([{**group,'speaker_ids':[]}],rec['speakers']))==1


def test_invalid_overlap_text_cannot_partially_change_answer(editor):
    rec,save=editor;original=deepcopy(rec)
    assert save(speaker_id='overlap',speaker_ids=['a','b'],speaker_texts={'missing':'invented'}).status_code==400
    assert rec==original
    assert save(speaker_id='overlap',speaker_ids=['a','b'],speaker_texts={'a':'x'*4001}).status_code==400
    assert rec==original


def test_typing_existing_name_reassigns_only_answer_and_never_renames_cluster(editor):
    rec,save=editor
    rec['segments'].append({'start':12,'end':13,'speaker_id':'a','text':'Later same cluster.'})
    rec['voice_references']=[{'id':'a','name':'Fictional Ana','start':0,'end':2}]
    original=deepcopy(rec)
    response=save(speaker_name='Fictional Ben')
    assert response.status_code==200
    assert response.json()['answer_groups'][0]['speaker_id']=='b'
    assert rec['speakers']==original['speakers']
    assert rec['voice_references']==original['voice_references']
    assert rec['segments'][-1]==original['segments'][-1]


def test_unknown_name_can_be_corrected_without_renaming_other_unknowns(editor):
    rec,save=editor
    rec['segments'][0]['speaker_id']='unknown'
    rec['segments'][1]['speaker_id']='unknown'
    original=deepcopy(rec['segments'][2:])
    response=save(speaker_name='Fictional Clara')
    assert response.status_code==200
    assert rec['segments'][2:]==original
    assert response.json()['answer_groups'][0]['speaker_id'] not in ('unknown','a','b')


def test_direct_simultaneous_edit_preserves_other_voice_and_shared_timing(editor):
    rec,save=editor
    save(speaker_id='overlap',speaker_ids=['a','b'],speaker_texts={'a':'Voice A.','b':'Voice B.'})
    response=save(source_speaker_id='a',speaker_id='a',text='Corrected A.',speaker_name='Fictional Clara')
    assert response.status_code==200
    group=response.json()['answer_groups'][0]
    assert group['speaker_id']=='overlap' and 'a' not in group['speaker_ids']
    assert group['speaker_texts']['b']=='Voice B.'
    assert 'Corrected A.' in group['speaker_texts'].values()
    assert rec['speakers'][0]['name']=='Fictional Ana'
    assert (group['start'],group['end'])==(0,2.8)
