"""Create an explicitly fictional UI fixture from Windows synthetic speech.

This does not run ASR or measure accuracy and never reads user recordings.
"""
import json,sys
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.audio import read_audio,RATE

root=Path(__file__).resolve().parent.parent/'.cache/readme-demo'
lines=json.loads((root/'demo-lines.json').read_text(encoding='utf-8-sig'))
rid='d'*32
folder=root/'data/recordings'/rid;folder.mkdir(parents=True,exist_ok=True)
parts=[];turns=[];segments=[];speakers={};cursor=0
for i,line in enumerate(lines):
    samples=read_audio(root/f'voice-{i}.wav');start=cursor+.5;end=start+len(samples)/RATE
    parts.extend([np.zeros(RATE//2,dtype=np.float32),samples]);cursor=end
    sid=line['speaker'];turns.append(dict(start=start,end=end,speaker_id=sid))
    segments.append(dict(start=start,end=end,speaker_id=sid,text=line['text']))
    if sid not in speakers:speakers[sid]=dict(id=sid,name=line['name'],sample_start=start,sample_end=min(end,start+4),seconds=0,evidence=line['text'],suggested=False,confirmed=True)
    speakers[sid]['seconds']+=end-start
sf.write(folder/'original.wav',np.concatenate(parts),RATE,subtype='PCM_16')
record=dict(id=rid,title='Community planning · fictional demo',filename='demo-meeting.wav',duration=cursor,created_at='2026-10-27T00:00:00Z',completed_at='2026-10-27T00:00:00Z',status='complete',detected_language='en',speakers=list(speakers.values()),turns=turns,segments=segments,overlap_regions=[],cleaned=False,warnings=[])
(folder/'recording.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print('Fictional demo ready:',root)
