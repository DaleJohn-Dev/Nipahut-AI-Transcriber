"""Idle polling must not repeatedly parse and regroup completed transcripts."""
from fastapi.testclient import TestClient
from app import server, storage, readability
import random


def test_conditional_recording_poll_skips_grouping_and_observes_edits(tmp_path, monkeypatch):
    rid = 'a' * 32
    folder = tmp_path / rid
    folder.mkdir()
    monkeypatch.setattr(storage, 'RECORDINGS', tmp_path)
    rec = {'id': rid, 'segments': [{'start': 0, 'end': 1, 'speaker_id': 'a', 'text': 'Hello'}]}
    storage.save_recording(rec)
    original = readability.with_answers
    calls = []
    def counted(value):
        calls.append(1)
        return original(value)
    monkeypatch.setattr(readability, 'with_answers', counted)
    client = TestClient(server.app)
    first = client.get(f'/api/recordings/{rid}')
    assert first.status_code == 200
    etag = first.headers['etag']
    for _ in range(5):
        unchanged = client.get(f'/api/recordings/{rid}', headers={'If-None-Match': etag})
        assert unchanged.status_code == 304 and unchanged.content == b''
    assert len(calls) == 1
    rec['segments'][0]['text'] = 'Corrected answer'
    storage.save_recording(rec)
    changed = client.get(f'/api/recordings/{rid}', headers={'If-None-Match': etag})
    assert changed.status_code == 200 and changed.headers['etag'] != etag
    assert changed.json()['answer_groups'][0]['text'] == 'Corrected answer'
    assert len(calls) == 2


def test_recording_index_reuses_json_but_refreshes_atomic_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'RECORDINGS', tmp_path)
    rid = 'b' * 32
    (tmp_path / rid).mkdir()
    rec = {'id': rid, 'created_at': '2026-10-28', 'title': 'Before'}
    storage.save_recording(rec)
    assert storage.list_recording_summaries()[0]['title'] == 'Before'
    with monkeypatch.context() as patch:
        patch.setattr(storage, 'read_json', lambda _: (_ for _ in ()).throw(AssertionError('Reparsed unchanged recording')))
        assert storage.list_recording_summaries()[0]['title'] == 'Before'
    rec['title'] = 'After'
    storage.save_recording(rec)
    assert storage.list_recording_summaries()[0]['title'] == 'After'
    (tmp_path / rid / 'recording.json').unlink()
    assert storage.list_recording_summaries() == []


def test_directory_inventory_is_bounded_and_expires(tmp_path, monkeypatch):
    now = [0]
    monkeypatch.setattr(storage.time, 'monotonic', lambda: now[0])
    calls = []
    monkeypatch.setattr(storage, '_directory_bytes', lambda _: calls.append(1) or len(calls))
    assert storage.directory_bytes(tmp_path) == 1
    now[0] = 29
    assert storage.directory_bytes(tmp_path) == 1
    now[0] = 31
    assert storage.directory_bytes(tmp_path) == 2


def test_interval_lookup_matches_overlap_rules_including_nested_intervals():
    rng = random.Random(42)
    intervals = []
    for _ in range(300):
        start = rng.randrange(100)
        intervals.append({'start': start, 'end': start + rng.randrange(1, 50)})
    index = readability._interval_index(intervals)
    for _ in range(1000):
        start, end = rng.randrange(150), rng.randrange(150)
        expected = any(min(r['end'], end) > max(r['start'], start) for r in intervals)
        assert readability._intersects(index, start, end) == expected
