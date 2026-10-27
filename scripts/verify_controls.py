"""Verify model lifecycle, job exclusivity, cancellation and retained original audio."""
import hashlib
import time
from pathlib import Path
import httpx

client = httpx.Client(base_url='http://127.0.0.1:8765', timeout=60)

def wait():
    for _ in range(120):
        state = client.get('/api/state').json()
        if state['job']['state'] != 'running':
            assert state['job']['state'] != 'error', state['job']
            return state
        time.sleep(.25)
    raise TimeoutError('Operation did not stop')

if __name__ == '__main__':
    state = wait()
    for mid in ['whisper-small','diarization','qwen-0.6b']:
        response = client.post(f'/api/models/{mid}/load')
        response.raise_for_status()
        state = wait()
        assert next(m for m in state['models'] if m['id']==mid)['loaded']
        client.post(f'/api/models/{mid}/unload').raise_for_status()
        state = wait()
        assert not next(m for m in state['models'] if m['id']==mid)['loaded']
        print(mid, 'load/unload PASS', flush=True)
    with Path('test-results/two-speaker-test.wav').open('rb') as f:
        response = client.post('/api/recordings', files={'file':('Cancellation test.wav',f,'audio/wav')})
    response.raise_for_status()
    rid = response.json()['id']
    wait()
    before = client.get(f'/api/recordings/{rid}/audio/original').content
    client.post(f'/api/recordings/{rid}/process').raise_for_status()
    assert client.post(f'/api/recordings/{rid}/process').status_code == 409
    for _ in range(100):
        job = client.get('/api/state').json()['job']
        if job['stage'] == 'transcribe':
            break
        time.sleep(.1)
    client.post('/api/jobs/cancel').raise_for_status()
    state = wait()
    assert state['job']['state'] == 'cancelled', state['job']
    assert client.get(f'/api/recordings/{rid}').json()['status'] == 'cancelled'
    after = client.get(f'/api/recordings/{rid}/audio/original').content
    assert hashlib.sha256(before).digest() == hashlib.sha256(after).digest()
    client.delete(f'/api/recordings/{rid}').raise_for_status()
    print('PASS: processing exclusivity, cancellation and original-audio preservation', flush=True)
