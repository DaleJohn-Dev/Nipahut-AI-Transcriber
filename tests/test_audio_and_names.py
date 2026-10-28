import numpy as np
from app.audio import RATE, clean_audio, decode_file, spectrogram_png
import soundfile as sf
from PIL import Image
import io
import pytest
from app.pipeline import phrase_names, assign_speakers, llm_names

def seg(text, sid='speaker_00', start=0):
    return {'start': start, 'end': start + 4, 'text': text, 'speaker_id': sid}

def test_self_introductions_multilingual():
    segments = [seg('Hi, I’m Alice from design.'), seg('Ako po si Juan Dela Cruz.', 'speaker_01', 5), seg('Maayong adlaw. Ako si Maria.', 'speaker_02', 10)]
    result = phrase_names(segments, 60)
    assert result['speaker_00']['name'] == 'Alice'
    assert result['speaker_01']['name'] == 'Juan Dela Cruz'
    assert result['speaker_02']['name'] == 'Maria'
    assert result['speaker_01']['evidence'] == segments[1]['text']

def test_ambiguous_or_third_person_names_are_not_assigned():
    assert phrase_names([seg('Alice will speak next.'), seg('I am working with Ben.'), seg('I am the manager.')], 60) == {}
    assert phrase_names([seg('I am Alice.'), seg('I am Ben.')], 60) == {}
    assert phrase_names([seg('I am Alice.', start=120)], 60)['speaker_00']['name']=='Alice'
    assert phrase_names([seg('I am Alice.', 'unknown')], 60) == {}

def test_names_without_intro_prefix_in_opening_turn():
    result=phrase_names([seg('Maria Elena Santos, researcher sa Manila.','speaker_02',22),
        seg('Ana Clara Reyes from Cebu.','speaker_03',28),
        seg('Ako naman po si Liza Cruz?','speaker_01',12)],90)
    assert result['speaker_02']['name']=='Maria Elena Santos'
    assert result['speaker_03']['name']=='Ana Clara Reyes'
    assert result['speaker_01']['name']=='Liza Cruz'
    assert result['speaker_02']['method']=='standalone_opening_candidate'
    assert not phrase_names([seg('John Smith from Manila will join later.')],90)
    assert not phrase_names([seg('Good Morning, researcher sa Manila.')],90)
    assert not phrase_names([seg('Let us start.'),seg('John Smith from Manila.',start=20)],90)


@pytest.mark.parametrize('text,name', [
    ('Maria Elena Santos.', 'Maria Elena Santos'),
    ('Good morning. Maria Santos.', 'Maria Santos'),
    ('Magandang umaga, Maria de la Cruz.', 'Maria de la Cruz'),
    ('Magandang umaga po. Maria Santos.', 'Maria Santos'),
    ('Maayong buntag. Ana L. Reyes, farmer sa Cebu.', 'Ana L. Reyes'),
    ('Juan, magsasaka.', 'Juan'),
    ('Ana Clara Reyes, teacher sa Manila.', 'Ana Clara Reyes'),
    ('Maria Santos taga-Cebu.', 'Maria Santos'),
])
def test_direct_names_are_opening_suggestions_with_exact_evidence(text, name):
    result = phrase_names([seg(text)], 90)['speaker_00']
    assert result['name'] == name
    assert result['evidence'] == text
    assert result['method'] == 'standalone_opening_candidate'


def test_greeting_and_fragmented_name_keep_timestamps_and_input():
    segments = [seg('Good morning.', start=0), seg('Maria', start=4),
                seg('Elena', start=8), seg('Santos, researcher.', start=12)]
    # The introduction joins at most twelve seconds; do not scan distant mentions.
    segments[0]['end'] = 1
    segments[1].update(start=1.2, end=2)
    segments[2].update(start=2.2, end=3)
    segments[3].update(start=3.2, end=5)
    from copy import deepcopy
    original = deepcopy(segments)
    result = phrase_names(segments, 90)['speaker_00']
    assert result['name'] == 'Maria Elena Santos'
    assert result['evidence'] == 'Good morning. Maria Elena Santos, researcher.'
    assert result['start'] == 0 and result['end'] == 5
    assert segments == original


@pytest.mark.parametrize('text', [
    'Maria Santos?', 'Maria Santos will speak next.', 'Please welcome Maria Santos.',
    'Maria Santos, farmer, said she will come later.', 'Thank You.', 'Good Morning.',
    'We Start.', 'Maria Santos is absent.',
])
def test_bare_mentions_questions_and_greetings_are_not_self_introductions(text):
    assert phrase_names([seg(text)], 90) == {}


def test_direct_candidates_respect_window_overlap_and_conflicting_names():
    assert not phrase_names([seg('Maria Santos.', start=91)], 90)
    assert not phrase_names([{**seg('Maria Santos.'), 'overlap': True}], 90)
    assert not phrase_names([seg('Maria', start=0), seg('Santos.', 'speaker_01', 4)], 90)
    assert not phrase_names([seg('Maria Santos.'), seg('I am Ana Reyes.', start=5)], 90)


def test_optional_llm_accepts_only_the_supported_direct_candidate(monkeypatch):
    from types import SimpleNamespace
    from app import pipeline
    proposed = ['Maria Santos']
    monkeypatch.setattr(pipeline.httpx, 'post', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {'choices': [{'message': {'content': '{"name": "' + proposed[0] + '"}'}}]}))
    assert llm_names([seg('Maria Santos, farmer.')], 90)['speaker_00']['name'] == 'Maria Santos'
    assert not llm_names([seg('Please welcome Maria Santos.')], 90)
    proposed[0] = 'Ana Reyes'
    assert not llm_names([seg('Maria Santos, farmer.')], 90)

def test_word_level_speaker_assignment_and_unmatched_words():
    segments = [{'start': 0, 'end': 6, 'text': 'Hi there friend', 'words': [
        {'start':0,'end':1,'word':' Hi'}, {'start':2,'end':3,'word':' there'}, {'start':5,'end':6,'word':' friend'}]}]
    turns = [{'start':0,'end':1.1,'speaker_id':'speaker_00'}, {'start':1.8,'end':3.1,'speaker_id':'speaker_01'}]
    result = assign_speakers(segments, turns)
    assert [r['speaker_id'] for r in result] == ['speaker_00', 'speaker_01', 'unknown']

def test_cleanup_keeps_original_and_timestamps():
    rng = np.random.default_rng(17)
    t = np.arange(RATE * 2 + 57) / RATE
    audio = (.2*np.sin(2*np.pi*220*t) + .03*rng.normal(size=len(t))).astype(np.float32)
    original = audio.copy()
    cleaned = clean_audio(audio, {'denoise':True,'dehiss':True,'hum':'60','normalize':True,'strength':.35})
    assert np.array_equal(audio, original)
    assert cleaned.shape == audio.shape
    assert np.isfinite(cleaned).all()
    assert np.max(np.abs(cleaned)) <= 1

def test_silence_stays_silent():
    audio = np.zeros(32_000, dtype=np.float32)
    cleaned = clean_audio(audio, {'denoise':True,'hum':'off','normalize':True})
    assert np.all(cleaned == 0)

def test_streamed_audio_conversion_and_real_spectrogram(tmp_path):
    rate = 48000
    t = np.arange(rate) / rate
    source = tmp_path / 'stereo.wav'
    tone = .2 * np.sin(2 * np.pi * 440 * t)
    sf.write(source, np.column_stack([tone, tone]), rate)
    output = tmp_path / 'analysis.wav'
    duration = decode_file(source, output)
    assert abs(duration - 1) < .01
    assert sf.info(output).channels == 1
    assert sf.info(output).samplerate == RATE
    png = spectrogram_png(output, width=128, height=64)
    img = Image.open(io.BytesIO(png))
    assert img.size == (128, 64)
    assert np.asarray(img).std() > 5

def test_failed_decode_does_not_leave_partial_audio(tmp_path):
    source = tmp_path / 'broken.wav'
    source.write_bytes(b'not an audio file')
    target = tmp_path / 'analysis.wav'
    with pytest.raises(Exception):
        decode_file(source, target)
    assert not target.exists()
    assert not target.with_suffix('.wav.part').exists()


def test_late_mentions_do_not_rename_but_explicit_self_introductions_can():
    assert not phrase_names([seg('We spoke to Maria Santos yesterday.',start=1800)],90)
    assert not phrase_names([seg('This is Maria Santos.',start=1800)],90)
    assert not phrase_names([seg('She said I am Maria Santos.',start=1800)],90)
    result=phrase_names([seg('Ako po si Maria Santos.',start=1800)],90)
    assert result['speaker_00']['name']=='Maria Santos'

@pytest.mark.parametrize('question',['What is your name?','Anong pangalan niyo?','Ano po ang pangalan ninyo?'])
def test_name_question_allows_immediate_response_after_opening_window(question):
    result=phrase_names([seg(question,'speaker_00',1800),seg('Maria Santos.','speaker_01',1805)],90)
    assert result['speaker_01']['name']=='Maria Santos'
    assert result['speaker_01']['method']=='name_question_response'
    assert not phrase_names([seg(question,'speaker_00',1800),seg('Maria Santos.','speaker_01',1900)],90)


def test_name_question_does_not_identify_another_person_in_same_voice():
    assert not phrase_names([seg('What is your name?',start=1800),seg('Maria Santos.',start=1805)],90)
    assert not phrase_names([{**seg('Ako si Maria Santos.'),'identity_review':True}],90)
