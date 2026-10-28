"""Bounded, local two-source ASR. Mixed words are never copied between voices."""
import multiprocessing as mp
import queue
import time
import numpy as np
from .audio import RATE


def windows(groups, duration):
    result=[]
    for group in sorted(groups,key=lambda g:g['start']):
        if group['end']-group['start']>16:
            continue
        start=max(0,group['start']-1.5);end=min(duration,group['end']+1.5)
        if result and end-result[-1]['start']<=20 and start<=result[-1]['end']:
            result[-1]['end']=max(result[-1]['end'],end);result[-1]['groups'].append(group)
        else:result.append({'start':start,'end':end,'groups':[group]})
    return result


def solo_centers(audio,rec,embed,check):
    from .diarization import overlap_regions
    overlaps=overlap_regions(rec.get('turns',[]))
    people={s['id'] for s in rec['speakers'] if s.get('identity_status')!='unresolved'}
    candidates={sid:[] for sid in people}
    for turn in rec.get('turns',[]):
        if turn['speaker_id'] not in people or turn.get('identity_review'):continue
        spans=[(turn['start'],turn['end'])]
        for region in overlaps:
            spans=[part for a,b in spans for part in ((a,min(b,region['start'])),(max(a,region['end']),b)) if part[1]>part[0]]
        candidates[turn['speaker_id']].extend((a,min(b,a+5)) for a,b in spans if b-a>=1.2)
    centers={}
    for sid,spans in candidates.items():
        vectors=[]
        for a,b in sorted(spans,key=lambda r:r[1]-r[0],reverse=True)[:3]:
            check();v=embed(audio,a,b)
            if v is not None:vectors.append(v)
        if vectors:
            v=np.mean(vectors,axis=0);norm=np.linalg.norm(v)
            if norm>1e-8:centers[sid]=v/norm
    return centers


def match_sources(vectors,centers):
    """Reject weak/ambiguous matches and never assign both outputs to one person."""
    matches=[]
    for vector in vectors:
        scores=sorted(((float(v@vector),sid) for sid,v in centers.items()),reverse=True) if vector is not None else []
        best=scores[0] if scores else (0,None)
        margin=best[0]-(scores[1][0] if len(scores)>1 else 0)
        matches.append(best[1] if best[0]>=.4 and margin>=.08 else None)
    if len(matches)==2 and matches[0] is not None and matches[0]==matches[1]:return [None,None]
    return matches


def run_inference(folder,rec,opts,progress=lambda p:None,check=lambda:None):
    from .models import manager
    from .readability import answer_groups
    from .separation import MODEL_ID,separate_clip,source_signature
    from .voice_profiles import extractor
    from .audio_edits import apply_silences
    from .audio import read_audio
    signature=source_signature(folder,rec)
    cached=[entry for entry in rec.get('overlap_transcripts',[]) if entry.get('source_signature')==signature and entry.get('asr_model')==opts['asr_model'] and entry.get('speaker_model')==opts['speaker_model']]
    finished={entry['fingerprint'] for entry in cached}
    groups=[g for g in answer_groups(rec) if (g.get('overlap') or g.get('speaker_id')=='overlap') and not g.get('edited') and g['fingerprint'] not in finished]
    batches=windows(groups,rec['duration']);results=list(cached)
    if not batches:return results
    audio=apply_silences(read_audio(folder/'original.wav'),rec.get('silenced_ranges',[]))
    embed=extractor(opts['speaker_model']);centers=solo_centers(audio,rec,embed,check)
    manager.load(MODEL_ID);manager.load(opts['asr_model'])
    language={'filipino':'tl','taglish':None,'cebuano':None,'bicolano':None,'auto':None}.get(opts['language'],opts['language'])
    try:
        for batch_index,batch in enumerate(batches):
            check();progress(batch_index/max(1,len(batches)))
            start,end=batch['start'],batch['end']
            sources=separate_clip(manager.loaded[MODEL_ID],audio[round(start*RATE):round(end*RATE)],check)
            # Highly correlated estimates are not evidence of two recovered voices.
            if np.min(np.std(sources,axis=0))<1e-6 or abs(float(np.corrcoef(sources.T)[0,1]))>.85:continue
            vectors=[embed(sources[:,i],0,len(sources)/RATE) for i in range(2)]
            matched=match_sources(vectors,centers);source_words=[]
            for i in range(2):
                check()
                sample=np.ascontiguousarray(sources[:,i])
                stream,_=manager.loaded[opts['asr_model']].transcribe(sample,language=language,beam_size=5,
                    word_timestamps=True,vad_filter=True,condition_on_previous_text=False,
                    no_speech_threshold=.6,log_prob_threshold=-1.0)
                words=[]
                for segment in stream:
                    check()
                    if segment.avg_logprob < -1 or segment.no_speech_prob>.6:continue
                    words.extend({'start':start+w.start,'end':start+w.end,'word':w.word} for w in (segment.words or []))
                source_words.append(words)
            for group in batch['groups']:
                rows=[]
                for i,words in enumerate(source_words):
                    chosen=[w for w in words if group['start']<=(w['start']+w['end'])/2<group['end']]
                    text=''.join(w['word'] for w in chosen).strip()
                    if not text:continue
                    rows.append({'speaker_id':matched[i] or 'unknown','source':i,'text':text,'words':chosen,
                                 'identity_review':matched[i] is None,'method':'sepformer_whamr_whisper'})
                distinct=len(rows)==2 and rows[0]['text'].casefold()!=rows[1]['text'].casefold()
                accepted=(distinct and all(r['speaker_id']!='unknown' for r in rows)
                          and len(set(group.get('speaker_ids',[])))<=2)
                results.append({'fingerprint':group['fingerprint'],'start':group['start'],'end':group['end'],
                                'sources':rows,'accepted':accepted,'source_signature':signature,'asr_model':opts['asr_model'],
                                'speaker_model':opts['speaker_model']})
        progress(1);return results
    finally:
        manager.unload(MODEL_ID);manager.unload(opts['asr_model'])


def _worker(folder,rec,opts,events):
    try:
        from pathlib import Path
        events.put(('result',run_inference(Path(folder),rec,opts,lambda p:events.put(('progress',p)))))
    except Exception as exc:events.put(('error',str(exc)))


def transcribe_overlaps(folder,rec,opts,progress,check):
    context=mp.get_context('spawn');events=context.Queue()
    process=context.Process(target=_worker,args=(str(folder),rec,opts,events),daemon=True);process.start()
    exited=None
    try:
        while True:
            check()
            try:kind,value=events.get(timeout=.15)
            except queue.Empty:
                if not process.is_alive():
                    exited=exited or time.monotonic()
                    if time.monotonic()-exited>1:raise RuntimeError('Overlap transcription worker stopped unexpectedly.')
                continue
            if kind=='progress':progress(value)
            elif kind=='result':return value
            else:raise RuntimeError('Overlap transcription: '+value)
    finally:
        if process.is_alive():process.terminate()
        process.join(3)
        if process.is_alive():process.kill();process.join()
        events.close();process.close()
