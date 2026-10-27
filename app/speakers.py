"""Optional turn-level refinement when the requested speaker count is not recovered."""
import numpy as np
import sherpa_onnx as so
from sklearn.cluster import AgglomerativeClustering
from .storage import MODELS
from .audio import RATE

def refine_turns(audio, turns, count, threshold=.35, progress=lambda p: None, check=lambda: None, model_id='diarization'):
    """Re-embed speech turns independently; retain their original time boundaries."""
    extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(
        model=str(MODELS / model_id / 'embedding.onnx'), num_threads=2, provider='cpu'))
    vectors, spans = [], []
    # Bound clustering memory. Refinement is intended for short/medium recordings.
    candidates = [t for t in turns if t['end'] - t['start'] >= .7]
    if len(candidates) > 1200:
        candidates = candidates[::max(1, len(candidates) // 1200)]
    for i, turn in enumerate(candidates):
        check()
        start = int(turn['start'] * RATE)
        end = int(min(turn['end'], turn['start'] + 5) * RATE)
        sample = np.ascontiguousarray(audio[start:end], dtype=np.float32)
        if len(sample) < int(.7 * RATE):
            continue
        stream = extractor.create_stream()
        stream.accept_waveform(sample_rate=RATE, waveform=sample)
        stream.input_finished()
        if not extractor.is_ready(stream):
            continue
        vector = np.asarray(extractor.compute(stream), dtype=np.float32)
        norm = np.linalg.norm(vector)
        if not np.isfinite(vector).all() or norm < 1e-8:
            continue
        vectors.append(vector / norm)
        spans.append(turn)
        progress((i + 1) / max(1, len(candidates)))
    if len(vectors) < max(2, count):
        return turns
    matrix = np.asarray(vectors)
    labels = AgglomerativeClustering(n_clusters=count if count else None,
        distance_threshold=None if count else threshold, metric='cosine', linkage='average').fit_predict(matrix)
    centroids = []
    for label in sorted(set(labels)):
        center = matrix[labels == label].mean(axis=0)
        centroids.append(center / max(np.linalg.norm(center), 1e-8))
    centers = np.asarray(centroids)
    assignments = {id(span): int(label) for span, label in zip(spans, labels)}
    # Short turns inherit the closest adjacent embedded speech turn, rather than
    # asking the speaker model to identify a few milliseconds of audio.
    output = []
    for turn in turns:
        label = assignments.get(id(turn))
        if label is None:
            closest = min(range(len(spans)), key=lambda j: abs((spans[j]['start']+spans[j]['end'])/2 - (turn['start']+turn['end'])/2))
            label = int(labels[closest])
        output.append({**turn, 'speaker_id': f'refined_{label}'})
    return output
