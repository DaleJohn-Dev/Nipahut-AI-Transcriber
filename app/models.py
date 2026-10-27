"""Explicit downloads; inference loads ONLY project-local files, never the network."""
import gc
import hashlib
import io
import json
import os
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path
import httpx
from .storage import MODELS, require_space, write_json, read_json, directory_bytes

GITHUB = 'https://github.com/k2-fsa/sherpa-onnx/releases/download'
CATALOG = {
    'whisper-small': {'label': 'Whisper small · multilingual', 'role': 'transcription', 'size': 490_000_000, 'license': 'MIT',
                      'source': 'https://huggingface.co/Systran/faster-whisper-small'},
    'whisper-base': {'label': 'Whisper base · smaller / faster', 'role': 'transcription', 'size': 150_000_000, 'license': 'MIT',
                     'source': 'https://huggingface.co/Systran/faster-whisper-base'},
    'whisper-turbo': {'label': 'Whisper large-v3-turbo · multilingual', 'role': 'transcription', 'size': 1_650_000_000, 'license': 'MIT',
                     'source': 'https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo', 'repo':'dropbox-dash/faster-whisper-large-v3-turbo'},
    'diarization': {'label': 'Pyannote segmentation + WeSpeaker · ONNX', 'role': 'diarization', 'size': 36_000_000,
                    'license': 'MIT segmentation / Apache-2.0 runtime & WeSpeaker', 'source': 'https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html'},
    'diarization-campplus': {'label': 'Pyannote + CAM++ · meeting voices', 'role': 'diarization', 'size': 29_000_000,
                    'license': 'Apache-2.0 / MIT segmentation', 'source': 'https://github.com/modelscope/3D-Speaker', 'requires': 'diarization'},
    'diarization-eres2net': {'label': 'Pyannote + ERes2NetV2 · alternative', 'role': 'diarization', 'size': 73_000_000,
                    'license': 'Apache-2.0 / MIT segmentation', 'source': 'https://github.com/modelscope/3D-Speaker', 'requires': 'diarization'},
    'rules': {'label': 'Introduction phrases · built in', 'role': 'names', 'size': 0, 'license': 'MIT', 'source': ''},
    'qwen-0.6b': {'label': 'Qwen3 0.6B · local language model', 'role': 'names', 'size': 680_000_000,
                  'license': 'Apache-2.0 weights / MIT llama.cpp', 'source': 'https://huggingface.co/Qwen/Qwen3-0.6B-GGUF'},
}

class ModelManager:
    def __init__(self):
        self.loaded = {}
        self.llama = None
        self.llama_log = None
        self.diarization_config = None
        self.diarization_configs = {}

    def state(self):
        result = []
        for mid, spec in CATALOG.items():
            local = MODELS / mid
            installed = mid == 'rules' or (local / 'manifest.json').is_file()
            size = directory_bytes(local) if local.exists() else 0
            result.append({'id': mid, **spec, 'installed': installed, 'loaded': mid in self.loaded or mid == 'rules', 'disk_bytes': size})
        return result

    def download(self, mid, progress=lambda p, text: None, check=lambda: None):
        if mid not in CATALOG:
            raise ValueError('Unknown model')
        if mid == 'rules':
            return
        folder = MODELS / mid
        if (folder / 'manifest.json').exists():
            return
        require_space(CATALOG[mid]['size'])
        folder.mkdir(exist_ok=True)
        downloads = []
        hashes = {}
        if mid.startswith('whisper-'):
            size = mid.split('-')[1]
            repo = CATALOG[mid].get('repo', f'Systran/faster-whisper-{size}')
            with httpx.Client(follow_redirects=True, timeout=60) as client:
                response = client.get(f'https://huggingface.co/api/models/{repo}')
                response.raise_for_status()
                metadata = response.json()
                revision = metadata['sha']
            available = {item['rfilename'] for item in metadata['siblings']}
            if not {'config.json','tokenizer.json','model.bin'}.issubset(available):
                raise RuntimeError('The upstream Whisper model is missing required inference files.')
            for name in ['config.json', 'tokenizer.json', 'preprocessor_config.json', 'vocabulary.txt', 'vocabulary.json', 'shared_vocabulary.json', 'model.bin']:
                if name not in available:
                    continue
                downloads.append((f'https://huggingface.co/{repo}/resolve/{revision}/{name}', name))
        elif mid == 'diarization':
            downloads = [
                (f'{GITHUB}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2', 'segmentation.tar.bz2'),
                (f'{GITHUB}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx', 'embedding.onnx'),
                ('https://raw.githubusercontent.com/wenet-e2e/wespeaker/master/LICENSE', 'WESPEAKER-LICENSE'),
            ]
        elif mid in ('diarization-campplus', 'diarization-eres2net'):
            self.download('diarization', progress, check)
            model_name = '3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx' if mid == 'diarization-campplus' else '3dspeaker_speech_eres2netv2_sv_zh-cn_16k-common.onnx'
            downloads = [(f'{GITHUB}/speaker-recongition-models/{model_name}', 'embedding.onnx'),
                         ('https://raw.githubusercontent.com/modelscope/3D-Speaker/main/LICENSE', '3DSPEAKER-LICENSE')]
        elif mid == 'qwen-0.6b':
            downloads = [
                ('https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf', 'model.gguf'),
                ('https://github.com/ggml-org/llama.cpp/releases/download/b9000/llama-b9000-bin-win-cpu-x64.zip', 'llama.zip'),
                ('https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/LICENSE', 'QWEN-LICENSE'),
                ('https://raw.githubusercontent.com/ggml-org/llama.cpp/b9000/LICENSE', 'LLAMA-LICENSE'),
            ]
        completed = 0
        for url, filename in downloads:
            check()
            target = folder / filename
            if target.exists():
                completed += target.stat().st_size
                hashes[filename] = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
                continue
            temp = target.with_suffix(target.suffix + '.part')
            try:
                with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(60, read=180)) as client:
                    with client.stream('GET', url, headers={'User-Agent': 'NipahutAITranscriber/0.1'}) as response:
                        response.raise_for_status()
                        received = 0
                        digest = hashlib.sha256()
                        with temp.open('wb') as f:
                            for block in response.iter_bytes(512 * 1024):
                                check()
                                f.write(block)
                                digest.update(block)
                                received += len(block)
                                progress(min(.99, (completed + received) / CATALOG[mid]['size']), f'Downloading {CATALOG[mid]["label"]} · {(completed + received)/1e6:.0f} MB')
                temp.replace(target)
                hashes[filename] = digest.hexdigest()
                completed += received
            except Exception:
                temp.unlink(missing_ok=True)
                raise
        if mid == 'diarization':
            with tarfile.open(folder / 'segmentation.tar.bz2') as archive:
                for member in archive.getmembers():
                    name = Path(member.name).name
                    if member.isfile() and name in ('model.onnx', 'LICENSE', 'README.md'):
                        source = archive.extractfile(member)
                        if source:
                            (folder / ('segmentation.onnx' if name == 'model.onnx' else 'SEGMENTATION-' + name)).write_bytes(source.read())
            (folder / 'segmentation.tar.bz2').unlink()
            if not (folder / 'segmentation.onnx').is_file():
                raise RuntimeError('Segmentation archive did not contain the model')
        if mid == 'qwen-0.6b':
            binary = folder / 'runtime'
            binary.mkdir(exist_ok=True)
            with zipfile.ZipFile(folder / 'llama.zip') as archive:
                for name in archive.namelist():
                    filename = Path(name).name
                    if filename == 'llama-server.exe' or filename.endswith('.dll'):
                        (binary / filename).write_bytes(archive.read(name))
            (folder / 'llama.zip').unlink()
        write_json(folder / 'manifest.json', {'id': mid, 'license': CATALOG[mid]['license'], 'source': CATALOG[mid]['source'], 'sha256': hashes})
        progress(1, 'Download complete')

    def load(self, mid):
        if mid in self.loaded or mid == 'rules':
            return
        if mid not in CATALOG or not (MODELS / mid / 'manifest.json').exists():
            raise RuntimeError('Download this model in Settings first.')
        folder = MODELS / mid
        if mid.startswith('whisper-'):
            from faster_whisper import WhisperModel
            obj = WhisperModel(str(folder), device='cpu', compute_type='int8', cpu_threads=max(1, min(4, (os.cpu_count() or 4) // 2)), local_files_only=True)
            self.loaded[mid] = obj
        elif mid.startswith('diarization'):
            import sherpa_onnx as so
            config = so.OfflineSpeakerDiarizationConfig(
                segmentation=so.OfflineSpeakerSegmentationModelConfig(
                    pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(MODELS / 'diarization' / 'segmentation.onnx')),
                    num_threads=2, provider='cpu'),
                embedding=so.SpeakerEmbeddingExtractorConfig(model=str(folder / 'embedding.onnx'), num_threads=2, provider='cpu'),
                clustering=so.FastClusteringConfig(num_clusters=-1, threshold=.5),
                min_duration_on=.25, min_duration_off=.4,
            )
            if not config.validate():
                raise RuntimeError('The local diarization model configuration is invalid.')
            self.diarization_config = config
            self.diarization_configs[mid] = config
            self.loaded[mid] = so.OfflineSpeakerDiarization(config)
        elif mid == 'qwen-0.6b':
            exe = folder / 'runtime' / 'llama-server.exe'
            if not exe.exists():
                raise RuntimeError('The CPU language-model runtime is not installed.')
            self.llama_log = (folder / 'runtime.log').open('w', encoding='utf-8')
            self.llama = subprocess.Popen([str(exe), '-m', str(folder / 'model.gguf'), '--host', '127.0.0.1', '--port', '8766', '-c', '4096', '-t', '4', '-ngl', '0', '--no-webui', '--jinja'],
                stdout=self.llama_log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for _ in range(120):
                if self.llama.poll() is not None:
                    self.unload(mid)
                    raise RuntimeError('Local language model could not start. See models/qwen-0.6b/runtime.log.')
                try:
                    if httpx.get('http://127.0.0.1:8766/health', timeout=1).status_code == 200:
                        self.loaded[mid] = True
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.5)
            self.unload(mid)
            raise RuntimeError('Language-model startup timed out.')

    def unload(self, mid):
        obj = self.loaded.pop(mid, None)
        if mid == 'qwen-0.6b' and self.llama:
            self.llama.terminate()
            try:
                self.llama.wait(5)
            except subprocess.TimeoutExpired:
                self.llama.kill()
                self.llama.wait()
            self.llama = None
            if self.llama_log:
                self.llama_log.close()
                self.llama_log = None
        del obj
        gc.collect()

    def shutdown(self):
        for mid in list(self.loaded):
            self.unload(mid)
        if self.llama:
            self.unload('qwen-0.6b')

manager = ModelManager()
