from app.diarization import normalize_turns, overlap_regions, overlap_summary, attribute_words
from app.server import Preferences, VoiceReference, VoiceReferences
from pydantic import ValidationError
import pytest

def turn(a, b, sid):
    return {'start': a, 'end': b, 'speaker_id': sid}

def test_simultaneous_speakers_preserved_and_same_speaker_merged():
    turns = normalize_turns([turn(0,2,'a'),turn(1,3,'a'),turn(1,2,'b'),turn(4,4,'c'),turn(float('nan'),5,'c')])
    assert turns == [turn(0,3,'a'),turn(1,2,'b')]
    regions = overlap_regions(turns)
    assert regions == [{'start':1.,'end':2.,'speaker_ids':['a','b']}]
    assert overlap_summary(turns, regions)['seconds'] == 1

def test_sequential_boundary_is_not_an_overlap():
    turns = [turn(0,1,'a'),turn(1,2,'b')]
    result = attribute_words([{'start':.8,'end':1.3,'text':'hello'}], turns)
    assert result[0]['speaker_id'] == 'b'
    assert not result[0]['overlap']

def test_mixed_words_are_not_duplicated_between_speakers():
    segments = [{'start':0,'end':3,'text':'one two three','words':[
        {'start':0,'end':.5,'word':'one'}, {'start':1.1,'end':1.5,'word':' two'}, {'start':2.5,'end':3,'word':' three'}]}]
    result = attribute_words(segments, [turn(0,2,'a'),turn(1,3,'b')])
    assert [s['speaker_id'] for s in result] == ['a','overlap','b']
    assert result[1]['speaker_ids'] == ['a','b']
    assert ' '.join(s['text'] for s in result) == 'one two three'

def test_ten_participants_have_independent_activity():
    turns = [turn(i*.5, i*.5+2,f's{i}') for i in range(10)]
    result = normalize_turns(turns)
    assert len({t['speaker_id'] for t in result}) == 10
    assert overlap_summary(result, overlap_regions(result))['max_detected_simultaneous'] == 4
    assert Preferences(speaker_count=10, speaker_model='diarization-campplus').speaker_count == 10

def test_references_reject_nonfinite_times_and_unsafe_ids():
    with pytest.raises(ValidationError):
        VoiceReference(id='../../file',name='Alice',start=0,end=3)
    with pytest.raises(ValidationError):
        VoiceReference(id='speaker_00',name='Alice',start=float('nan'),end=3)
    refs=[VoiceReference(id=f'speaker_{i:02}',name=f'Person {i}',start=i*3,end=i*3+2) for i in range(21)]
    with pytest.raises(ValidationError):VoiceReferences(references=refs)

def test_uncertainty_survives_merging_and_word_assignment():
    turns=normalize_turns([turn(0,2,'a'),{**turn(1,3,'a'),'identity_review':True}])
    result=attribute_words([{'start':1,'end':2,'text':'hello'}],turns)
    assert result[0]['identity_review']


def test_short_review_interval_does_not_contaminate_adjacent_confident_speech():
    spans = [
        {**turn(0,2,'a'),'identity_review':False},
        {**turn(2,3,'a'),'identity_review':True,'verification':'two_model_consensus'},
        {**turn(3,10,'a'),'identity_review':False},
    ]
    normalized = normalize_turns(spans)
    assert [(t['start'],t['end'],bool(t.get('identity_review'))) for t in normalized] == [
        (0,2,False),(2,3,True),(3,10,False)]
    assert sum(t['end']-t['start'] for t in normalized if t.get('identity_review')) == 1
    assert normalized[1]['verification'] == 'two_model_consensus'
    assert all('verification' not in t for t in (normalized[0],normalized[2]))
    words = [{'start':0,'end':10,'text':'one two three','words':[
        {'start':1,'end':1.5,'word':'one'},
        {'start':2.1,'end':2.5,'word':' two'},
        {'start':5,'end':5.5,'word':' three'}]}]
    assert [s['identity_review'] for s in attribute_words(words,normalized)] == [False,True,False]
    assert normalize_turns(normalized) == normalized


def test_overlaid_same_speaker_review_splits_without_duplicating_activity():
    spans = [turn(0,10,'a'),
        {**turn(2,3,'a'),'identity_review':True,'verification':'two_model_consensus'},
        {**turn(2.5,4,'a'),'identity_review':True},turn(1,5,'b')]
    normalized = normalize_turns(spans)
    a = [t for t in normalized if t['speaker_id']=='a']
    assert sum(t['end']-t['start'] for t in a) == 10
    assert all(first['end'] <= second['start'] for first,second in zip(a,a[1:]))
    assert sum(t['end']-t['start'] for t in a if t.get('identity_review')) == 2
    assert [(t['start'],t['end']) for t in a if t.get('verification')] == [(2,3)]
    assert overlap_regions(normalized) == [{'start':1,'end':5,'speaker_ids':['a','b']}]


def test_verification_boundaries_and_conflicts_remain_local():
    normalized = normalize_turns([
        {**turn(0,4,'a'),'verification':'first_check'},
        {**turn(2,6,'a'),'verification':'second_check'},
    ])
    assert [(t['start'],t['end']) for t in normalized] == [(0,2),(2,4),(4,6)]
    assert normalized[0]['verification'] == 'first_check'
    assert normalized[2]['verification'] == 'second_check'
    assert 'verification' not in normalized[1]
    assert normalized[1]['annotation_conflicts']['verification'] == ['first_check','second_check']
    assert normalize_turns(normalized) == normalized


def test_confident_equivalent_annotations_merge_but_gaps_do_not():
    normalized = normalize_turns([turn(0,2,'a'),{**turn(1,3,'a'),'identity_review':False},turn(4,5,'a')])
    assert normalized == [turn(0,3,'a'),turn(4,5,'a')]

def test_corrected_name_is_kept_with_its_voice_reference(monkeypatch):
    from app import server
    rec={'speakers':[{'id':'speaker_00','name':'Guess','confirmed':False}],
         'voice_references':[{'id':'speaker_00','name':'Guess','start':1,'end':4,'confirmed':False}]}
    monkeypatch.setattr(server,'idle',lambda:None)
    monkeypatch.setattr(server,'get_recording',lambda _:rec)
    monkeypatch.setattr(server,'save_recording',lambda _:None)
    server.edit_speaker('0'*32,'speaker_00',server.SpeakerEdit(name='Correct Name',confirmed=True))
    assert rec['voice_references'][0]['name']=='Correct Name'
    assert rec['voice_references'][0]['name_confirmed']
    assert not rec['voice_references'][0]['confirmed']  # Name review does not certify the audio sample.
