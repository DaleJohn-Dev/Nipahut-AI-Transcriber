"""Refresh small upstream license texts; never downloads model weights or recordings."""
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parent.parent
SOURCES={
    'third-party/Whisper/LICENSE':'https://raw.githubusercontent.com/openai/whisper/main/LICENSE',
    'third-party/Qt-open-source/LGPL-3.0.txt':'https://www.gnu.org/licenses/lgpl-3.0.txt',
    'third-party/Qt-open-source/GPL-3.0.txt':'https://www.gnu.org/licenses/gpl-3.0.txt',
    'third-party/model-notices/SEGMENTATION-LICENSE':'https://huggingface.co/pyannote/segmentation-3.0/resolve/main/LICENSE',
    'third-party/model-notices/WESPEAKER-LICENSE':'https://raw.githubusercontent.com/wenet-e2e/wespeaker/master/LICENSE',
    'third-party/model-notices/3DSPEAKER-LICENSE':'https://raw.githubusercontent.com/modelscope/3D-Speaker/main/LICENSE',
    'third-party/model-notices/QWEN-LICENSE':'https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/LICENSE',
    'third-party/model-notices/LLAMA-LICENSE':'https://raw.githubusercontent.com/ggml-org/llama.cpp/b9000/LICENSE',
}
if __name__=='__main__':
    with httpx.Client(follow_redirects=True,timeout=45) as client:
        for name,url in SOURCES.items():
            path=ROOT/name
            if path.exists():continue
            response=client.get(url);response.raise_for_status()
            if len(response.content)>250_000:raise RuntimeError('Unexpected license size')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(response.content)
            print('Retained upstream notice:',name,flush=True)
