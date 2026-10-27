"""Reversible time masks; speaker lanes are labels over a mixed recording."""
import math
import numpy as np

def normalize_silences(ranges, duration):
    spans=[]
    for item in ranges:
        a,b=float(item['start']),float(item['end'])
        if not math.isfinite(a) or not math.isfinite(b) or not 0<=a<b<=duration:
            raise ValueError('Choose a valid time range within this recording.')
        spans.append({'start':a,'end':b})
    spans.sort(key=lambda x:x['start']);output=[]
    for item in spans:
        if output and item['start']<=output[-1]['end']:
            output[-1]['end']=max(output[-1]['end'],item['end'])
        else:output.append(dict(item))
    return output

def restore_range(ranges, start, end):
    output=[]
    for item in ranges:
        if item['end']<=start or item['start']>=end:output.append(dict(item));continue
        if item['start']<start:output.append({'start':item['start'],'end':start})
        if item['end']>end:output.append({'start':end,'end':item['end']})
    return output

def apply_silences(audio, ranges, rate=16000):
    if not ranges:return audio
    out=audio.copy()
    for span in normalize_silences(ranges,len(audio)/rate):
        a,b=int(span['start']*rate),min(len(out),int(span['end']*rate))
        out[a:b]=0
        # Short fades stay inside the edit; adjacent voices remain untouched.
        n=min(int(.005*rate),max(0,(b-a)//2))
        if n:
            out[a:a+n]=audio[a:a+n]*np.linspace(1,0,n,dtype=np.float32)
            out[b-n:b]=audio[b-n:b]*np.linspace(0,1,n,dtype=np.float32)
    return out
