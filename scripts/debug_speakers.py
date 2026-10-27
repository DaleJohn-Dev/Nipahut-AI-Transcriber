import numpy as np
import sherpa_onnx as so
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.audio import read_audio
e = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model='models/diarization/embedding.onnx', num_threads=2))
embeddings = []
for path in sorted(Path('test-results').glob('voice-*.wav')):
    x = read_audio(path)
    stream = e.create_stream()
    stream.accept_waveform(sample_rate=16000, waveform=x)
    stream.input_finished()
    v = np.array(e.compute(stream))
    v /= np.linalg.norm(v)
    embeddings.append(v)
    print(path.name, x.shape, v[:3], flush=True)
print(np.array(embeddings) @ np.array(embeddings).T, flush=True)
