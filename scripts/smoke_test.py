"""Exercise real local audio inference over the public app API."""
import json
import sys
import time
from pathlib import Path
import httpx

BASE = 'http://127.0.0.1:8765'
client = httpx.Client(base_url=BASE, timeout=60)

def wait(allow_error=False):
    previous = ''
    for _ in range(900):
        state = client.get('/api/state').json()
        job = state['job']
        key = f'{job["state"]}: {job["stage"]}: {job["message"]}'
        if key != previous:
            print(key, flush=True)
            previous = key
        if job['state'] != 'running':
            if job['state'] == 'error' and not allow_error:
                raise RuntimeError(job['message'])
            return state
        time.sleep(1)
    raise TimeoutError('Processing did not finish')

if __name__ == '__main__':
    state = wait(allow_error=True)
    prefs = state['settings']
    prefs.update(language='en', speaker_count=0 if '--auto' in sys.argv else 2, name_model='qwen-0.6b' if '--llm' in sys.argv else 'rules')
    prefs['cleanup'].update(denoise=True, dehiss=True, hum='off', normalize=True)
    response = client.put('/api/settings', json=prefs)
    response.raise_for_status()
    if '--reuse' in sys.argv:
        rid = state['recordings'][0]['id']
    else:
        with Path('test-results/two-speaker-test.wav').open('rb') as f:
            response = client.post('/api/recordings', files={'file': ('Synthetic two-speaker test.wav', f, 'audio/wav')})
        response.raise_for_status()
        rid = response.json()['id']
        wait()
    response = client.post(f'/api/recordings/{rid}/process')
    response.raise_for_status()
    wait()
    result = client.get(f'/api/recordings/{rid}').json()
    Path('test-results/smoke-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'id':rid,'duration':result['duration'],'speakers':result['speakers'], 'warnings':result['warnings']}, indent=2), flush=True)
    assert result['status'] == 'complete'
    assert len(result['speakers']) == 2
    assert result['segments']
    names = {s['name'].casefold() for s in result['speakers']}
    assert 'david' in names and 'sarah' in names, names
    for variant in ['original', 'cleaned']:
        response = client.get(f'/api/recordings/{rid}/spectrogram?variant={variant}')
        response.raise_for_status()
        assert response.content.startswith(b'\x89PNG')
    for fmt in ['txt','srt','json']:
        response = client.get(f'/api/recordings/{rid}/export/{fmt}')
        response.raise_for_status()
        Path(f'test-results/transcript.{fmt}').write_bytes(response.content)
    print('PASS: real transcription, 2-speaker diarization, introduction names, cleanup, spectrograms and all exports', flush=True)
