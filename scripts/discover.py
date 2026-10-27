import json, urllib.request
from pathlib import Path

for url in [
    'https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/speaker-recongition-models',
    'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest',
    'https://huggingface.co/api/models/Systran/faster-whisper-small',
]:
    req = urllib.request.Request(url, headers={'User-Agent': 'NipahutAITranscriber-local-build'})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if 'assets' in data:
        print(data['tag_name'])
        for a in data['assets']:
            if ('wespeaker_en_voxceleb_resnet34' in a['name'] or ('win' in a['name'] and 'cpu' in a['name'])):
                print(a['name'], a['size'], a['browser_download_url'])
    else:
        print(data.get('sha'), [s['rfilename'] for s in data['siblings']])
