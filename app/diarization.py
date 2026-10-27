"""Interval operations retain simultaneous speakers without duplicating ASR text."""
from collections import Counter
import math

def normalize_turns(turns, duration=None):
    """Union same-speaker activity without spreading annotations in time.

    Active annotations are combined only over their actual intersection. A
    reviewed interval therefore cannot mark adjoining confident speech for
    review. Conflicting provenance is retained as a conflict rather than
    selecting an arbitrary verification claim.
    """
    grouped = {}
    for turn in turns:
        start, end = float(turn['start']), float(turn['end'])
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        start = max(0., start)
        end = min(end, duration) if duration is not None else end
        if end <= start:
            continue
        grouped.setdefault(turn['speaker_id'], []).append({**turn, 'start': start, 'end': end})
    output = []
    for sid, spans in grouped.items():
        events = {}
        for index, span in enumerate(spans):
            events.setdefault(span['start'], []).append((index, 1))
            events.setdefault(span['end'], []).append((index, -1))
        active = {}
        merged = []
        previous = None
        for point in sorted(events):
            if previous is not None and point > previous and active:
                annotation = _active_annotation(active.values())
                span = {'start': previous, 'end': point, 'speaker_id': sid, **annotation}
                if (merged and merged[-1]['end'] == previous
                        and _annotation(merged[-1]) == annotation):
                    merged[-1]['end'] = point
                else:
                    merged.append(span)
            for index, change in events[point]:
                if change > 0:
                    active[index] = spans[index]
                else:
                    active.pop(index, None)
            previous = point
        output.extend(merged)
    return sorted(output, key=lambda t: (t['start'], t['end'], t['speaker_id']))


def _annotation(turn):
    # Missing and explicit False both mean no review requirement. Canonicalizing
    # them allows otherwise equivalent adjacent confident spans to merge.
    return {key: value for key, value in turn.items()
            if key not in ('start', 'end', 'speaker_id', 'identity_review')
            and not (key == 'verification' and value is None)} | (
                {'identity_review': True} if turn.get('identity_review') else {})


def _active_annotation(spans):
    values = {}
    review = False
    for span in spans:
        review = review or bool(span.get('identity_review'))
        for key, value in _annotation(span).items():
            if key == 'identity_review':
                continue
            unique = values.setdefault(key, [])
            if not any(value == existing for existing in unique):
                unique.append(value)
    annotation, conflicts = {}, {}
    for key, unique in values.items():
        if len(unique) == 1:
            annotation[key] = unique[0]
        else:
            conflicts[key] = unique
    if conflicts:
        # Do not represent conflicting verification evidence as one verified
        # scalar value. Keep its provenance only on the intersecting interval.
        inherited = annotation.pop('annotation_conflicts', {})
        annotation['annotation_conflicts'] = {**inherited, **conflicts}
    if review:
        annotation['identity_review'] = True
    return annotation

def overlap_regions(turns, minimum=.04):
    events = {}
    for turn in turns:
        events.setdefault(turn['start'], []).append((turn['speaker_id'], 1))
        events.setdefault(turn['end'], []).append((turn['speaker_id'], -1))
    active, regions, previous = Counter(), [], None
    for point in sorted(events):
        speakers = sorted(s for s, count in active.items() if count > 0)
        if previous is not None and point > previous and len(speakers) > 1:
            if regions and regions[-1]['speaker_ids'] == speakers and abs(regions[-1]['end'] - previous) < 1e-6:
                regions[-1]['end'] = point
            else:
                regions.append({'start': previous, 'end': point, 'speaker_ids': speakers})
        for sid, change in events[point]:
            active[sid] += change
        previous = point
    return [r for r in regions if r['end'] - r['start'] >= minimum]

def overlap_summary(turns, regions):
    return {'regions': len(regions), 'seconds': round(sum(r['end']-r['start'] for r in regions), 3),
            'max_detected_simultaneous': max([len(r['speaker_ids']) for r in regions] or [1 if turns else 0]),
            'model_max_simultaneous': 2,
            'overlap_transcription': 'mixed_audio_review_required'}

def attribute_words(segments, turns):
    regions = overlap_regions(turns)
    output = []
    for segment in segments:
        words = segment.get('words') or [{'start': segment['start'], 'end': segment['end'], 'word': segment['text']}]
        for word in words:
            start, end = float(word['start']), float(word['end'])
            if end < start:
                end = start
            hits = {}
            identity_review = False
            for turn in turns:
                if turn['start'] > end:
                    break
                amount = max(0., min(end, turn['end']) - max(start, turn['start']))
                if amount > 0:
                    identity_review = identity_review or turn.get('identity_review',False)
                    sid = turn['speaker_id']
                    hits[sid] = hits.get(sid, 0.) + amount
            simultaneous = set()
            for region in regions:
                if region['start'] >= end:
                    break
                if min(end, region['end']) - max(start, region['start']) >= min(.04, max(.005, (end-start)*.2)):
                    simultaneous.update(region['speaker_ids'])
            candidates = sorted(simultaneous)
            is_overlap = len(candidates) > 1
            if is_overlap:
                sid, attribution = 'overlap', 'ambiguous_overlap'
            elif hits:
                ranked = sorted(hits.items(), key=lambda pair: (-pair[1], pair[0]))
                sid = ranked[0][0]
                candidates = [sid]
                attribution = 'speaker_turn'
            else:
                sid, candidates, attribution = 'unknown', [], 'unassigned'
            text = word.get('word', '')
            if (output and output[-1]['speaker_id'] == sid and output[-1]['speaker_ids'] == candidates
                    and output[-1]['identity_review'] == identity_review
                    and start-output[-1]['end'] < .8 and not output[-1]['text'].rstrip().endswith(('.', '?', '!'))):
                output[-1]['text'] += text
                output[-1]['end'] = end
            else:
                output.append({'id': len(output), 'start': start, 'end': end, 'text': text,
                               'speaker_id': sid, 'speaker_ids': candidates, 'overlap': is_overlap,
                               'identity_review': identity_review,
                               'attribution': attribution})
    for segment in output:
        segment['text'] = segment['text'].strip()
    return output
