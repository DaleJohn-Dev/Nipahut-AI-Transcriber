"""Optional local enrollment from clean, user-reviewable reference clips.

Only single-speaker regions are reclassified. Mixed audio cannot safely provide
an isolated voice embedding; overlap keeps native turns with review flags.
"""
import numpy as np
import sherpa_onnx as so
from .audio import RATE
from .storage import MODELS
from .diarization import normalize_turns

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
        if b-a<.7:
            mixed.append((a,b,ids));continue
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
