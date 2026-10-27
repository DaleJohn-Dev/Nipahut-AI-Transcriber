"""Bounded recording-wide voice matching. Uncertainty is never a new person."""
from collections import Counter, defaultdict
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster, cut_tree
from scipy.spatial.distance import pdist
from .diarization import normalize_turns

MAX_SPEAKERS = 20
MAX_WINDOWS = 1200


def regions(turns, key='speaker'):
    events = defaultdict(list)
    for turn in turns:
        if turn['end'] > turn['start']:
            events[float(turn['start'])].append((turn[key], 1))
            events[float(turn['end'])].append((turn[key], -1))
    active, previous, result = Counter(), None, []
    for point in sorted(events):
        ids = tuple(sorted((sid for sid, n in active.items() if n > 0), key=str))
        if previous is not None and point > previous and ids:
            if result and result[-1]['ids'] == ids and result[-1]['end'] == previous:
                result[-1]['end'] = point
            else:
                result.append({'start': previous, 'end': point, 'ids': ids})
        for sid, delta in events[point]:
            active[sid] += delta
        previous = point
    return result


def sample_windows(activity, budget=MAX_WINDOWS):
    """Cover native groups and recording time; never embed overlapping mixtures."""
    candidates = defaultdict(list)
    for region in activity:
        if len(region['ids']) != 1 or region['end']-region['start'] < 1.2:
            continue
        length = min(4., region['end']-region['start'])
        for start in sorted(set(np.linspace(region['start'], region['end']-length, 3))):
            candidates[region['ids'][0]].append({'native': region['ids'][0], 'start': float(start), 'end': float(start+length)})
    groups = []
    for choices in candidates.values():
        # Prefer long speech; retain temporal diversity rather than adjacent duplicates.
        choices.sort(key=lambda r: (-(r['end']-r['start']), r['start']))
        selected = []
        for item in choices:
            if all(abs(item['start']-other['start']) >= 1.2 for other in selected):
                selected.append(item)
            if len(selected) == 3:
                break
        groups.append(selected)
    groups.sort(key=lambda group: group[0]['start'])
    if len(groups) > budget:
        groups = [groups[i] for i in np.linspace(0, len(groups)-1, budget, dtype=int)]
    output = []
    for index in range(3):
        for group in groups:
            if index < len(group) and len(output) < budget:
                output.append(group[index])
    return output


def unit(vector):
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector/norm if vector.ndim == 1 and np.isfinite(vector).all() and norm > 1e-8 else None


def fingerprints(windows, vectors, count=0, threshold=.5, profiles=()):
    """Global average-link clustering plus score/margin/purity rejection.

    The maximum is an acceptance limit, not a command to merge excess identities.
    Thresholds are conservative engineering defaults, not calibrated probabilities.
    """
    if not 0 <= count <= MAX_SPEAKERS:
        raise ValueError('Choose automatic counting or 1â€“20 speakers.')
    valid = [(w, unit(v)) for w, v in zip(windows, vectors) if v is not None]
    valid = [(w, v) for w, v in valid if v is not None]
    if not valid:
        return {}, {'windows': 0, 'accepted_profiles': 0, 'candidate_clusters': 0, 'profile_names': {}}
    windows, vectors = zip(*valid)
    matrix = np.asarray(vectors)
    if len(matrix) == 1:
        labels = np.zeros(1, dtype=int)
    else:
        tree = linkage(np.clip(pdist(matrix, metric='cosine'), 0, 2), method='average')
        labels = (cut_tree(tree, n_clusters=[min(count, len(matrix))])[:, 0] if count else
                  fcluster(tree, t=float(threshold), criterion='distance')-1)
    candidates = []
    for label in sorted(set(labels)):
        indices = np.flatnonzero(labels == label)
        center = unit(matrix[indices].mean(axis=0))
        seconds = sum(windows[i]['end']-windows[i]['start'] for i in indices)
        if center is not None and (len(indices) >= 2 or seconds >= 2.5) and np.min(matrix[indices]@center) >= .45:
            candidates.append((seconds, indices, center))
    candidates.sort(key=lambda item: (-item[0], windows[item[1][0]]['start']))
    kept = candidates[:count or MAX_SPEAKERS]
    kept.sort(key=lambda item: min(windows[i]['start'] for i in item[1]))
    if not kept:
        return {}, {'windows': len(matrix), 'accepted_profiles': 0, 'candidate_clusters': len(set(labels)), 'profile_names': {}}
    centers = np.asarray([item[2] for item in kept])
    profile_names, identities, used_profiles = {}, [], set()
    for index, center in enumerate(centers):
        scores = []
        for profile in profiles:
            prototypes = [unit(v) for v in profile['vectors']]
            matches = [float(center@v) for v in prototypes if v is not None and len(v) == len(center)]
            if matches:
                scores.append((max(matches), profile))
        scores.sort(key=lambda item: -item[0])
        if (scores and scores[0][0] >= .65 and
            scores[0][0]-(scores[1][0] if len(scores)>1 else 0) >= .10):
            profile = scores[0][1]
            sid = 'profile_' + profile['id']
            # One saved identity may legitimately have several acoustic prototypes.
            used_profiles.add(sid)
            profile_names[sid] = profile['name']
        else:
            sid = f'speaker_{index:02d}'
        identities.append(sid)
    votes, totals = defaultdict(Counter), Counter()
    scores = matrix@centers.T
    for window, row in zip(windows, scores):
        duration = window['end']-window['start']
        totals[window['native']] += duration
        order = np.argsort(row)[::-1]
        best = int(order[0])
        margin = float(row[best]-(row[order[1]] if len(order)>1 else 0))
        # Acoustic modes that map to the same saved person must not compete.
        other = [float(value) for j, value in enumerate(row) if identities[j] != identities[best]]
        margin = float(row[best])-max(other) if other else float(row[best])
        if row[best] >= .50 and margin >= .06:
            votes[window['native']][identities[best]] += duration
    mapping = {}
    for native, total in totals.items():
        if votes[native]:
            sid, support = votes[native].most_common(1)[0]
            if support/total >= .75:
                mapping[native] = sid
    return mapping, {'windows': len(matrix), 'candidate_clusters': len(set(labels)),
                     'accepted_profiles': len(set(identities)), 'overflow_clusters': max(0,len(candidates)-len(kept)),
                     'matched_saved_profiles': len(used_profiles), 'profile_names': profile_names,
                     'maximum_speakers': count or MAX_SPEAKERS, 'human_verified': False,
                     'thresholds': {'similarity': .50, 'margin': .06, 'native_vote_purity': .75,
                                    'saved_similarity': .65, 'saved_margin': .10}}


def apply_identities(activity, mapping):
    output = []
    for region in activity:
        assigned = [mapping.get(native, 'unknown') for native in region['ids']]
        duplicates = Counter(sid for sid in assigned if sid != 'unknown')
        unresolved = 0
        for sid in assigned:
            review = sid == 'unknown' or duplicates[sid] > 1
            if review:
                sid = 'unknown' if len(assigned) == 1 else f'unresolved_{unresolved}'
                unresolved += 1
            output.append({'start':region['start'], 'end':region['end'], 'speaker_id':sid,
                           'identity_review':review or sid.startswith('profile_')})
    return normalize_turns(output)


def classify(audio, native_turns, embed, count=0, threshold=.5, profiles=(), progress=lambda p:None, budget=MAX_WINDOWS):
    activity = regions(native_turns)
    windows = sample_windows(activity, min(MAX_WINDOWS, budget))
    vectors = []
    for i, window in enumerate(windows):
        vectors.append(embed(audio, window['start'], window['end']))
        progress((i+1)/max(1,len(windows)))
    mapping, diagnostics = fingerprints(windows, vectors, count, threshold, profiles)
    turns = apply_identities(activity, mapping)
    diagnostics.update(native_groups=len({t['speaker'] for t in native_turns}),
                       uncertain_speaker_seconds=round(sum(t['end']-t['start'] for t in turns if t.get('identity_review')),3),
                       method='bounded_global_voice_embeddings')
    return turns, diagnostics
