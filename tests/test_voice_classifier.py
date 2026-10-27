import numpy as np
from app.voice_classifier import fingerprints, apply_identities, classify, regions, sample_windows, MAX_WINDOWS
from app.diarization import overlap_regions


def test_712_native_groups_reuse_twenty_global_voices():
    rng=np.random.default_rng(42)
    windows=[{'native':i,'start':i*4.,'end':i*4.+3} for i in range(712)]
    basis=np.eye(20,dtype=np.float32)
    vectors=[basis[i%20]+rng.normal(0,.01,20) for i in range(712)]
    mapping, diagnostics=fingerprints(windows,vectors)
    assert len(set(mapping.values()))==20
    for voice in range(20):
        assert len({mapping[i] for i in range(voice,712,20)})==1
    assert diagnostics['accepted_profiles']==20
    assert not diagnostics['human_verified']


def test_excess_distinct_voices_are_rejected_not_forced_together():
    windows=[{'native':i,'start':i*4.,'end':i*4.+3} for i in range(50)]
    mapping, diagnostics=fingerprints(windows,np.eye(50))
    assert len(set(mapping.values()))<=20 and len(mapping)==20
    assert diagnostics['overflow_clusters']==30
    output=apply_identities(regions([{'start':w['start'],'end':w['end'],'speaker':w['native']} for w in windows]),mapping)
    assert {t['speaker_id'] for t in output if t.get('identity_review')}=={'unknown'}


def test_ambiguous_native_group_does_not_pollute_identity():
    windows=[{'native':i//2,'start':i*4.,'end':i*4.+3} for i in range(6)]
    vectors=[[1,0],[1,0],[0,1],[0,1],[1,0],[0,1]]
    mapping,_=fingerprints(windows,vectors)
    assert mapping[0]!=mapping[1] and 2 not in mapping


def test_overlap_never_collapses_when_both_native_labels_match_same_person():
    activity=regions([{'start':0,'end':4,'speaker':'a'},{'start':1,'end':3,'speaker':'b'}])
    output=apply_identities(activity,{'a':'speaker_00','b':'speaker_00'})
    mixed=overlap_regions(output)
    assert mixed==[{'start':1.,'end':3.,'speaker_ids':['unresolved_0','unresolved_1']}]
    assert sum(t['end']-t['start'] for t in output)==6


def test_long_uncertain_recording_has_one_unassigned_lane_not_thousands():
    native=[{'start':i,'end':i+.2,'speaker':i} for i in range(5000)]
    output,diagnostics=classify(None,native,lambda *args: (_ for _ in ()).throw(AssertionError('Short speech must not be embedded')))
    assert {t['speaker_id'] for t in output}=={'unknown'}
    assert diagnostics['native_groups']==5000


def test_embedding_budget_and_solo_only_sampling():
    native=[{'start':i*5.,'end':i*5.+4,'speaker':i} for i in range(2000)]
    activity=regions(native+[{'start':1,'end':3,'speaker':'overlap'}])
    windows=sample_windows(activity)
    assert len(windows)<=MAX_WINDOWS
    assert min(w['start'] for w in windows)<10 and max(w['end'] for w in windows)>9900
    assert all(w['end']<=1 or w['start']>=3 for w in windows)


def test_saved_voice_matching_is_reviewable_and_model_dimensions_must_match():
    windows=[{'native':0,'start':0,'end':4},{'native':1,'start':6,'end':10}]
    profiles=[{'id':'saved-a','name':'Fictional Ana','vectors':[[1,0]]},
              {'id':'other-model','name':'Wrong dimension','vectors':[[0,0,1]]}]
    mapping,diagnostics=fingerprints(windows,[[1,0],[0,1]],profiles=profiles)
    assert mapping[0]=='profile_saved-a' and mapping[1].startswith('speaker_')
    assert diagnostics['profile_names']=={'profile_saved-a':'Fictional Ana'}
    assert apply_identities(regions([{'start':0,'end':4,'speaker':0}]),mapping)[0]['identity_review']


def test_no_fingerprint_for_invalid_vectors():
    mapping,_=fingerprints([{'native':0,'start':0,'end':4}],[np.array([float('nan'),0])])
    assert mapping=={}
