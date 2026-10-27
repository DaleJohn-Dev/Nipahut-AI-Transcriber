"""Reference diarization scoring: zero collar, overlap included, no audio copies.

DER is meaningful only against independently checked human speaker activity.
Reference regions must be explicit so partially annotated audio is never scored
as if everything outside its labels were verified silence.
"""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

MAX_TURNS = 200_000
MAX_IDENTITIES = 256
MAX_REGIONS = 10_000


def _interval(start, end, label):
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}: timestamps must be numbers') from exc
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError(f'{label}: require finite 0 <= start < end')
    return start, end


def _unassigned(speaker):
    return speaker in {'unknown', 'overlap', 'unassigned'} or speaker.startswith('unresolved_')


def _turns(turns, reference=False):
    if len(turns) > MAX_TURNS:
        raise ValueError(f'Too many turns (limit {MAX_TURNS})')
    output = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise ValueError(f'Turn {index}: expected an object')
        try:
            start, end = _interval(turn['start'], turn['end'], f'Turn {index}')
            speaker = turn['speaker_id']
        except KeyError as exc:
            raise ValueError(f'Turn {index}: require start, end and speaker_id') from exc
        if not isinstance(speaker, str) or not speaker.strip() or len(speaker) > 256:
            raise ValueError(f'Turn {index}: require a nonempty speaker_id of at most 256 characters')
        if reference and _unassigned(speaker):
            raise ValueError('Human reference requires identified speaker labels; exclude unannotated regions instead')
        output.append({'start': start, 'end': end, 'speaker_id': speaker})
    if len({t['speaker_id'] for t in output}) > MAX_IDENTITIES:
        raise ValueError(f'Too many identity labels (limit {MAX_IDENTITIES})')
    return output


def _regions(regions):
    if not regions:
        raise ValueError('Explicit scoring regions are required, e.g. [(0, 30)]')
    if len(regions) > MAX_REGIONS:
        raise ValueError(f'Too many scoring regions (limit {MAX_REGIONS})')
    spans = []
    for index, region in enumerate(regions):
        if isinstance(region, dict):
            start, end = region.get('start'), region.get('end')
        else:
            if not isinstance(region, (tuple, list)) or len(region) != 2:
                raise ValueError(f'Region {index}: expected a start/end pair')
            start, end = region
        spans.append(_interval(start, end, f'Region {index}'))
    spans.sort()
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _timeline(reference, hypothesis, regions):
    events = defaultdict(list)
    for kind, turns in [('reference', reference), ('hypothesis', hypothesis)]:
        for turn in turns:
            events[turn['start']].append((kind, turn['speaker_id'], 1))
            events[turn['end']].append((kind, turn['speaker_id'], -1))
    for start, end in regions:
        events[start].append(('region', '', 1))
        events[end].append(('region', '', -1))
    counts = {'reference': Counter(), 'hypothesis': Counter(), 'region': Counter()}
    points = sorted(events)
    output = []
    for index, point in enumerate(points[:-1]):
        for kind, speaker, change in events[point]:
            counts[kind][speaker] += change
        duration = points[index + 1] - point
        if duration <= 0 or counts['region'][''] <= 0:
            continue
        refs = frozenset(s for s, n in counts['reference'].items() if n > 0)
        hyps = frozenset(s for s, n in counts['hypothesis'].items() if n > 0)
        output.append((duration, refs, hyps))
    return output


def _components(timeline, mapping):
    miss = false_alarm = confusion = denominator = 0.
    for duration, refs, hyps in timeline:
        correct = len(refs.intersection(mapping[s] for s in hyps if s in mapping))
        miss += duration * max(0, len(refs) - len(hyps))
        false_alarm += duration * max(0, len(hyps) - len(refs))
        confusion += duration * (min(len(refs), len(hyps)) - correct)
        denominator += duration * len(refs)
    error = miss + false_alarm + confusion
    return {'miss_seconds': miss, 'false_alarm_seconds': false_alarm,
            'confusion_seconds': confusion, 'error_speaker_seconds': error,
            'reference_speaker_seconds': denominator,
            'der': error / denominator if denominator else None,
            'der_percent': 100 * error / denominator if denominator else None}


def score_diarization(reference, hypothesis, regions, *, reference_is_human=False, fixed_mapping=None):
    """Score speaker activity over verified regions, including simultaneous voices.

    Speaker IDs are optimally permuted globally by maximum co-occurring speech
    duration. App sentinel IDs (unknown, overlap, unresolved_*) are intentionally
    unmatchable and still count as hypothesized activity. DER can exceed 100%.
    Silence inside a supplied scoring region is treated as verified silence.
    Human verification is a caller assertion, not something software can infer.
    Use a fixed hypothesis-to-reference mapping to test actual known identities;
    optimal anonymous permutation alone cannot reveal a consistently swapped name.
    """
    spans = _regions(regions)
    reference = _turns(reference, reference=True)
    hypothesis = _turns(hypothesis)
    base = {'collar_seconds': 0., 'overlap_included': True,
            'scoring_regions': [{'start': a, 'end': b} for a, b in spans],
            'scored_duration_seconds': sum(b - a for a, b in spans),
            'reference_is_human': bool(reference_is_human),
            'mapping_mode': 'optimal_anonymous' if fixed_mapping is None else 'fixed_identity',
            'unassigned_policy': 'unmatchable_hypothesis_activity',
            'der': None, 'der_percent': None}
    if not reference_is_human:
        return {**base, 'status': 'not_scored',
                'reason': 'A human-verified reference is required; model agreement is not an error rate.'}
    timeline = _timeline(reference, hypothesis, spans)
    refs = sorted({s for _, speakers, _ in timeline for s in speakers})
    hyps = sorted({s for _, _, speakers in timeline for s in speakers if not _unassigned(s)})
    cooccurrence = np.zeros((len(refs), len(hyps)), dtype=np.float64)
    ref_index, hyp_index = {s: i for i, s in enumerate(refs)}, {s: i for i, s in enumerate(hyps)}
    for duration, active_refs, active_hyps in timeline:
        for ref in active_refs:
            for hyp in active_hyps:
                if hyp in hyp_index:
                    cooccurrence[ref_index[ref], hyp_index[hyp]] += duration
    mapping = {}
    if fixed_mapping is not None:
        if not isinstance(fixed_mapping, dict) or any(not isinstance(h, str) or not isinstance(r, str) for h, r in fixed_mapping.items()):
            raise ValueError('Fixed mapping must be an object of hypothesis speaker IDs to reference speaker IDs')
        if len(set(fixed_mapping.values())) != len(fixed_mapping):
            raise ValueError('Fixed identity mapping must be one-to-one')
        if any(_unassigned(h) or _unassigned(r) for h, r in fixed_mapping.items()):
            raise ValueError('Unassigned labels cannot be promoted to verified identities through a fixed mapping')
        all_reference_ids = {t['speaker_id'] for t in reference}
        for hyp in hyps:
            if hyp in fixed_mapping:
                if fixed_mapping[hyp] not in all_reference_ids:
                    raise ValueError(f'Fixed mapping target {fixed_mapping[hyp]!r} is absent from the reference')
                mapping[hyp] = fixed_mapping[hyp]
    elif refs and hyps:
        rows, columns = linear_sum_assignment(cooccurrence, maximize=True)
        mapping = {hyps[c]: refs[r] for r, c in zip(rows, columns) if cooccurrence[r, c] > 0}
    components = _components(timeline, mapping)
    overlap = [span for span in timeline if len(span[1]) > 1]
    return {**base, **components,
            'status': 'scored' if components['reference_speaker_seconds'] else 'no_reference_speech',
            'reference_speakers': len(refs),
            'hypothesis_speakers': len({s for _, _, speakers in timeline for s in speakers}),
            'speaker_mapping_hypothesis_to_reference': mapping,
            'reference_overlap_duration_seconds': sum(d for d, _, _ in overlap),
            'overlap_only': _components(overlap, mapping)}


def load_turns(path, recording_id=None):
    """Read an app result/JSON turn list or RTTM; do not combine recordings."""
    path = Path(path)
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError('Reference/result file exceeds the 64 MiB scoring limit')
    records = defaultdict(list)
    if path.suffix.lower() == '.rttm':
        for index, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            fields = line.split()
            if fields[0] != 'SPEAKER':
                continue
            if len(fields) < 8:
                raise ValueError(f'RTTM line {index}: expected at least 8 fields')
            try:
                start, duration = float(fields[3]), float(fields[4])
            except ValueError as exc:
                raise ValueError(f'RTTM line {index}: invalid onset/duration') from exc
            records[fields[1]].append({'start': start, 'end': start + duration, 'speaker_id': fields[7]})
    else:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            if 'turns' not in data:
                raise ValueError('JSON object must contain raw speaker turns, not transcript segments')
            records[str(data.get('recording_id', data.get('id', 'recording')))] = data['turns']
        elif isinstance(data, list):
            for turn in data:
                if not isinstance(turn, dict):
                    raise ValueError('JSON turns must be objects')
                records[str(turn.get('recording_id', 'recording'))].append(turn)
        else:
            raise ValueError('Expected a JSON turn list or recording object')
    if not records:
        return []
    if recording_id is not None:
        if recording_id not in records:
            raise ValueError(f'Recording {recording_id!r} not present in {path.name}')
        turns = records[recording_id]
    elif len(records) == 1:
        turns = next(iter(records.values()))
    else:
        raise ValueError('Multiple recordings found; select a recording ID explicitly')
    if not isinstance(turns, list):
        raise ValueError('turns must be a list')
    return _turns(turns)
