"""Optional local enrollment from clean, user-reviewable reference clips.

Only single-speaker regions are reclassified. Mixed audio cannot safely provide
an isolated voice embedding; overlap keeps native turns with review flags.
"""
import numpy as np
import sherpa_onnx as so
from .audio import RATE
from .storage import MODELS
from .diarization import normalize_turns

def extend_reference_continuity(turns, activity, reference_ids):
    """Fill only a short unmatched edge of a strongly supported solo utterance."""
    for region in activity:
        if len(region['ids'])!=1:continue
        parts=[t for t in turns if t['start']>=region['start'] and t['end']<=region['end']]
        matches=[t for t in parts if t.get('verification')=='partial_reference_consensus']
        identities={t['speaker_id'] for t in matches}
        matched=sum(t['end']-t['start'] for t in matches)
        length=region['end']-region['start']
        if len(identities)!=1 or matched<length*.7 or length-matched>2:continue
        sid=next(iter(identities))
        for t in parts:
            if t['speaker_id'] not in reference_ids and (t['start']==region['start'] or t['end']==region['end']):
                t.update(speaker_id=sid,identity_review=True,verification='reference_continuity_review')
    return turns

def match_partial_references(audio, turns, references, primary_id, secondary_id,
                             maximum=32, progress=lambda p:None, check=lambda:None,
                             reference_audio=None):
    """Open-set enrollment: known interviewers do not exhaust the participant list.

    Require agreement of two models for new matches. Other voices retain their
    discovered identities. The input reference excerpts are not test examples.
    """
    from .voice_profiles import extractor
    from .voice_classifier import regions
    extractors=[extractor(mid) for mid in (primary_id,secondary_id)]
    source=reference_audio if reference_audio is not None else audio
    centers=[]
    for embed in extractors:
        vectors=[embed(source,r['start'],r['end']) for r in references]
        if any(v is None for v in vectors):raise ValueError('A reference contains no usable voice embedding.')
        centers.append(np.asarray(vectors))
    reserved={r['id'] for r in references}
    ids=list(dict.fromkeys(t['speaker_id'] for t in turns if t['speaker_id']!='unknown' and not t['speaker_id'].startswith('unresolved_')))
    slots=(f'speaker_{i:02}' for i in range(100) if f'speaker_{i:02}' not in reserved)
    remap={sid:next(slots) for sid in ids}
    activity=regions(turns,key='speaker_id')
    output=[];matched=0.
    for i,region in enumerate(activity):
        check();progress(i/max(1,len(activity)))
        a,b=region['start'],region['end'];native=region['ids']
        if len(native)>1 or b-a<.7:
            output.extend({'start':a,'end':b,'speaker_id':remap.get(sid,sid),'identity_review':True} for sid in native)
            continue
        starts=sorted(set(np.linspace(a,max(a,b-2.5),max(1,int(np.ceil((b-a)/1.5))))))
        mids=[(x+min(b,x+2.5))/2 for x in starts]
        bounds=[a]+[(x+y)/2 for x,y in zip(mids,mids[1:])]+[b]
        for j,x in enumerate(starts):
            rankings=[]
            for embed,centers_for_model in zip(extractors,centers):
                vector=embed(audio,x,min(b,x+2.5))
                scores=centers_for_model@vector if vector is not None else np.zeros(len(references))
                order=np.argsort(scores)[::-1];best=int(order[0])
                rankings.append((best,float(scores[best]),float(scores[best]-(scores[order[1]] if len(order)>1 else 0))))
            first,second=rankings
            reliable=first[0]==second[0] and first[1]>=.5 and second[1]>=.4 and first[2]>=.08 and second[2]>=.08
            sid=references[first[0]]['id'] if reliable else remap.get(native[0],native[0])
            lo,hi=bounds[j:j+2]
            output.append({'start':lo,'end':hi,'speaker_id':sid,'identity_review':reliable or sid=='unknown' or sid.startswith('unresolved_'),
                           'verification':'partial_reference_consensus' if reliable else 'automatic_candidate'})
            if reliable:matched+=hi-lo
    output=extend_reference_continuity(output,activity,reserved)
    # Reserve space for known references without inventing identities for other
    # speech. Only the least-supported excess candidate lanes become unassigned.
    durations={sid:sum(t['end']-t['start'] for t in output if t['speaker_id']==sid) for sid in remap.values()}
    keep=set(sorted(durations,key=durations.get,reverse=True)[:max(0,maximum-len(reserved))])
    for turn in output:
        if turn['speaker_id'] in durations and turn['speaker_id'] not in keep:turn['speaker_id']='unknown'
    progress(1)
    return normalize_turns(output,len(audio)/RATE), {'method':'partial_reference_two_model_consensus',
        'reference_count':len(references),'matched_seconds':round(matched,3),
        'other_voices_retained':True,'human_verified':False,'maximum_speakers':maximum}

def enroll_and_match(audio, turns, references, model_id, progress=lambda p:None, check=lambda:None, reference_audio=None):
    extractor = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(
        model=str(MODELS/model_id/'embedding.onnx'), num_threads=2, provider='cpu'))
    def embed(a,b,reference=False):
        check()
        source=reference_audio if reference and reference_audio is not None else audio
        sample=np.ascontiguousarray(source[int(a*RATE):int(b*RATE)],dtype=np.float32)
        stream=extractor.create_stream();stream.accept_waveform(sample_rate=RATE,waveform=sample);stream.input_finished()
        if not extractor.is_ready(stream):
            return None
        v=np.asarray(extractor.compute(stream),dtype=np.float32)
        norm=np.linalg.norm(v)
        return v/norm if norm>1e-8 and np.isfinite(v).all() else None
    centers=[]
    for ref in references:
        v=embed(ref['start'],ref['end'],reference=True)
        if v is None:
            raise ValueError('A voice reference is too short or contains no usable speech.')
        centers.append(v)
    centers=np.asarray(centers)
    # Partition the timeline into regions with a stable active native speaker set.
    points=sorted({p for t in turns for p in (t['start'],t['end'])})
    regions=[]
    for a,b in zip(points,points[1:]):
        active=[t['speaker_id'] for t in turns if t['start']<=a and t['end']>=b]
        if not active:continue
        ids=tuple(sorted(set(active)))
        if regions and regions[-1][2]==ids and abs(regions[-1][1]-a)<1e-5:
            regions[-1]=(regions[-1][0],b,ids)
        else:regions.append((a,b,ids))
    classified=[]; votes={}; mixed=[]; uncertain=0.
    for index,(a,b,ids) in enumerate(regions):
        check();progress(index/max(1,len(regions)))
        if len(ids)>1:
            mixed.append((a,b,ids));continue
        if b-a<.35:
            mixed.append((a,b,ids));continue
        if b-a<.7:
            # Native cuts may split a short name in half. Pad the embedding only;
            # keep the actual attribution interval unchanged, and never pad into overlap.
            lo=max(0,a-.2);hi=min(len(audio)/RATE,b+.2)
            if any(len(rids)>1 and min(hi,rb)>max(lo,ra) for ra,rb,rids in regions):
                mixed.append((a,b,ids));continue
            v=embed(lo,hi);scores=centers@v if v is not None else np.zeros(len(centers))
            ranked=np.argsort(scores)[::-1];best=int(ranked[0]);score=float(scores[best]);margin=score-float(scores[ranked[1]]) if len(ranked)>1 else score
            reliable=score>=.4 and margin>=.1
            sid=references[best]['id'] if reliable else 'unknown'
            classified.append({'start':a,'end':b,'speaker_id':sid,'identity_review':True,'verification':'short_context_reference'})
            if reliable:
                votes.setdefault(ids[0],{}).setdefault(sid,0.);votes[ids[0]][sid]+=b-a
            else:uncertain+=b-a
            continue
        starts=list(np.arange(a,max(a,b-2.5)+.001,1.25))
        if not starts or b-(starts[-1]+2.5)>.3:starts.append(max(a,b-2.5))
        starts=sorted(set(starts));centres=[(x+min(b,x+2.5))/2 for x in starts]
        boundaries=[a]+[(x+y)/2 for x,y in zip(centres,centres[1:])]+[b]
        for j,x in enumerate(starts):
            v=embed(x,min(b,x+2.5))
            scores=centers@v if v is not None else np.zeros(len(centers))
            ranked=np.argsort(scores)[::-1];best=int(ranked[0]);score=float(scores[best]);margin=score-float(scores[ranked[1]]) if len(ranked)>1 else score
            reliable=score>=.30 and margin>=.065
            sid=references[best]['id'] if reliable else 'unknown'
            lo,hi=boundaries[j:j+2]
            classified.append({'start':lo,'end':hi,'speaker_id':sid,'identity_review':not reliable})
            if reliable:
                votes.setdefault(ids[0],{}).setdefault(sid,0.)
                votes[ids[0]][sid]+=hi-lo
            else:uncertain+=hi-lo
    mapping={};purity={}
    for native,counts in votes.items():
        best=max(counts,key=counts.get);fraction=counts[best]/sum(counts.values());purity[native]=fraction
        mapping[native]=best if fraction>=.6 else 'unknown'
    for a,b,ids in mixed:
        assigned=[mapping.get(sid,'unknown') for sid in ids]
        # Never silently collapse two concurrent native voices to one identity.
        assigned=[f'unresolved_{native}' if sid=='unknown' or assigned.count(sid)>1 else sid for native,sid in zip(ids,assigned)]
        for sid in set(assigned):classified.append({'start':a,'end':b,'speaker_id':sid,'identity_review':True})
    progress(1)
    return normalize_turns(classified,len(audio)/RATE), {'method':'clean_reference_windows','reference_count':len(references),
        'uncertain_single_speaker_seconds':round(uncertain,2),'native_reference_purity':purity,
        'overlap_identity_requires_review':True,'reference_names_verified':all(r.get('confirmed',False) for r in references)}

def verify_uncertain(audio, turns, references, primary_id, secondary_id, progress=lambda p:None, check=lambda:None, reference_audio=None):
    """Require independent model agreement; never infer identity from mixed turns."""
    extractors={mid:so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(
        model=str(MODELS/mid/'embedding.onnx'),num_threads=2,provider='cpu')) for mid in (primary_id,secondary_id)}
    def embed(mid,a,b,reference=False):
        check();extractor=extractors[mid];stream=extractor.create_stream()
        source=reference_audio if reference and reference_audio is not None else audio
        stream.accept_waveform(sample_rate=RATE,waveform=np.ascontiguousarray(source[int(a*RATE):int(b*RATE)],dtype=np.float32));stream.input_finished()
        if not extractor.is_ready(stream):return None
        v=np.asarray(extractor.compute(stream),dtype=np.float32);norm=np.linalg.norm(v)
        return v/norm if norm>1e-8 and np.isfinite(v).all() else None
    centers={mid:np.asarray([embed(mid,r['start'],r['end'],reference=True) for r in references]) for mid in extractors}
    output=[dict(t) for t in turns if t['speaker_id']!='unknown'];chunks=[]
    for t in turns:
        if t['speaker_id']!='unknown':continue
        count=max(1,int(np.ceil((t['end']-t['start'])/2.5)))
        edges=np.linspace(t['start'],t['end'],count+1)
        chunks.extend({**t,'start':float(a),'end':float(b)} for a,b in zip(edges,edges[1:]))
    resolved=0.
    for i,t in enumerate(chunks):
        check();progress(i/max(1,len(chunks)))
        if t['end']-t['start']<1.3:
            output.append(t);continue
        ranked=[]
        for mid in extractors:
            v=embed(mid,t['start'],t['end'])
            scores=centers[mid]@v if v is not None else np.zeros(len(references))
            order=np.argsort(scores)[::-1];best=int(order[0]);score=float(scores[best]);margin=score-float(scores[order[1]]) if len(order)>1 else score
            ranked.append((best,score,margin))
        primary,secondary=ranked
        if primary[0]==secondary[0] and primary[1]>=.25 and secondary[1]>=.35 and secondary[2]>=.10:
            t.update(speaker_id=references[primary[0]]['id'],identity_review=True,verification='two_model_consensus')
            resolved+=t['end']-t['start']
        output.append(t)
    progress(1)
    turns=normalize_turns(output,len(audio)/RATE)
    return turns,{'secondary_model':secondary_id,'consensus_seconds':round(resolved,3),
        'remaining_unassigned_seconds':round(sum(t['end']-t['start'] for t in turns if t['speaker_id']=='unknown'),3),
        'human_verified':False}
