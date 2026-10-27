import json
import pytest
from app.evaluation import load_turns, score_diarization


def turn(start, end, speaker):
    return {'start': start, 'end': end, 'speaker_id': speaker}


def score(ref, hyp, regions=((0, 10),)):
    return score_diarization(ref, hyp, regions, reference_is_human=True)


def test_permuted_speakers_and_overlap_are_perfect():
    ref = [turn(0, 5, 'Alice'), turn(3, 10, 'Bob')]
    result = score(ref, [turn(0, 5, '2'), turn(3, 10, '1')])
    assert result['der'] == 0
    assert result['reference_speaker_seconds'] == 12
    assert result['reference_overlap_duration_seconds'] == 2
    assert result['overlap_only']['der'] == 0
    assert result['speaker_mapping_hypothesis_to_reference'] == {'2': 'Alice', '1': 'Bob'}


def test_missing_second_overlapping_voice_counts_speaker_seconds():
    result = score([turn(0, 10, 'a'), turn(4, 6, 'b')], [turn(0, 10, 'x')])
    assert result['miss_seconds'] == 2
    assert result['false_alarm_seconds'] == result['confusion_seconds'] == 0
    assert result['der'] == pytest.approx(2 / 12)
    assert result['overlap_only']['der'] == .5


def test_false_alarms_include_verified_silence_and_can_exceed_100_percent():
    result = score([turn(0, 1, 'a')], [turn(0, 10, 'x'), turn(1, 10, 'y')])
    assert result['false_alarm_seconds'] == 18
    assert result['reference_speaker_seconds'] == 1
    assert result['der_percent'] == 1800


def test_global_identity_drift_is_confusion_not_a_new_per_turn_mapping():
    ref = [turn(0, 5, 'a'), turn(5, 10, 'b')]
    result = score(ref, [turn(0, 10, 'x')])
    assert result['confusion_seconds'] == 5
    assert result['miss_seconds'] == result['false_alarm_seconds'] == 0
    assert result['der'] == .5


def test_fixed_identities_expose_consistently_swapped_real_names():
    ref = [turn(0, 5, 'Alice'), turn(5, 10, 'Bob')]
    hyp = [turn(0, 5, 'Bob'), turn(5, 10, 'Alice')]
    assert score(ref, hyp)['der'] == 0
    fixed = score_diarization(ref, hyp, [(0, 10)], reference_is_human=True,
        fixed_mapping={'Alice': 'Alice', 'Bob': 'Bob'})
    assert fixed['der'] == 1
    assert fixed['mapping_mode'] == 'fixed_identity'


def test_fixed_identity_mapping_cannot_hide_unassigned_or_fragmented_clusters():
    ref = [turn(0, 10, 'Alice')]
    with pytest.raises(ValueError):
        score_diarization(ref, [turn(0, 10, 'unknown')], [(0, 10)], reference_is_human=True,
            fixed_mapping={'unknown': 'Alice'})
    with pytest.raises(ValueError):
        score_diarization(ref, [turn(0, 5, 'x'), turn(5, 10, 'y')], [(0, 10)], reference_is_human=True,
            fixed_mapping={'x': 'Alice', 'y': 'Alice'})


def test_partial_coverage_excludes_unannotated_recording():
    result = score([turn(0, 2, 'a')], [turn(0, 2, 'x'), turn(5, 100, 'y')], [(0, 3)])
    assert result['der'] == 0
    assert result['scored_duration_seconds'] == 3
    assert result['hypothesis_speakers'] == 1


def test_overlapping_regions_and_duplicate_same_speaker_do_not_double_count():
    result = score([turn(0, 6, 'a'), turn(2, 8, 'a')], [turn(0, 8, 'x')], [(0, 5), (3, 8)])
    assert result['der'] == 0
    assert result['reference_speaker_seconds'] == result['scored_duration_seconds'] == 8


def test_twenty_speaker_scene_with_ten_simultaneous_voices():
    ref = [turn(i // 10 * 5, i // 10 * 5 + 5, f'person_{i}') for i in range(20)]
    hyp = [turn(t['start'], t['end'], f'cluster_{19-i}') for i, t in enumerate(ref)]
    result = score(ref, hyp)
    assert result['der'] == 0
    assert result['reference_speakers'] == 20
    assert result['reference_speaker_seconds'] == 100
    assert result['reference_overlap_duration_seconds'] == 10


def test_unknown_and_unresolved_do_not_become_verified_people_through_mapping():
    for sid in ['unknown', 'overlap', 'unassigned', 'unresolved_speaker_01']:
        result = score([turn(0, 10, 'a')], [turn(0, 10, sid)])
        assert result['der'] == 1
        assert result['confusion_seconds'] == 10
        assert result['speaker_mapping_hypothesis_to_reference'] == {}


def test_model_labels_alone_never_produce_an_error_rate():
    result = score_diarization([turn(0, 10, 'a')], [turn(0, 10, 'x')], [(0, 10)])
    assert result['status'] == 'not_scored'
    assert result['der'] is None


def test_silence_only_reference_does_not_divide_by_zero():
    result = score([], [turn(0, 10, 'x')])
    assert result['status'] == 'no_reference_speech'
    assert result['false_alarm_seconds'] == 10
    assert result['der'] is None


@pytest.mark.parametrize('bad', [turn(-1, 2, 'a'), turn(0, 0, 'a'), turn(0, float('inf'), 'a'), turn(float('nan'), 2, 'a')])
def test_invalid_intervals_are_rejected(bad):
    with pytest.raises(ValueError):
        score([bad], [])


def test_missing_regions_and_unidentified_reference_are_rejected():
    with pytest.raises(ValueError):
        score([], [], [])
    with pytest.raises(ValueError):
        score([turn(0, 10, 'unknown')], [])


def test_rttm_and_app_json_readers(tmp_path):
    reference = tmp_path / 'reference.rttm'
    reference.write_text('SPEAKER sample 1 0 5 <NA> <NA> Alice <NA> <NA>\nSPEAKER sample 1 3 7 <NA> <NA> Bob <NA> <NA>\n')
    hypothesis = tmp_path / 'hypothesis.json'
    hypothesis.write_text(json.dumps({'id': 'sample', 'turns': [turn(0, 5, 'x'), turn(3, 10, 'y')]}))
    assert score(load_turns(reference), load_turns(hypothesis))['der'] == 0


def test_multiple_recordings_require_explicit_selection(tmp_path):
    path = tmp_path / 'ref.rttm'
    path.write_text('SPEAKER one 1 0 1 <NA> <NA> a <NA> <NA>\nSPEAKER two 1 0 1 <NA> <NA> b <NA> <NA>\n')
    with pytest.raises(ValueError):
        load_turns(path)
    assert load_turns(path, 'two') == [turn(0, 1, 'b')]


def test_transcript_segments_are_not_mistaken_for_speaker_activity(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps({'segments': [turn(0, 1, 'overlap')]}))
    with pytest.raises(ValueError):
        load_turns(path)
