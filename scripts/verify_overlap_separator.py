"""One bounded two-voice separation check against known synthetic source signals.

Generate fictional source files with create_readme_demo.ps1 first. Results are
local diagnostics, never a claim about natural recordings or ten-way overlap.
"""
import argparse,itertools,json,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.audio import read_audio,RATE
from app.separation import load_separator,separate_clip,MODEL_ID
from app.storage import MODELS

def si_sdr(estimated,reference):
    estimated=estimated.astype(np.float64)-np.mean(estimated)
    reference=reference.astype(np.float64)-np.mean(reference)
    target=np.dot(estimated,reference)/(np.dot(reference,reference)+1e-12)*reference
    return float(10*np.log10((np.sum(target**2)+1e-12)/(np.sum((estimated-target)**2)+1e-12)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--first',default='.cache/readme-demo/voice-0.wav');parser.add_argument('--second',default='.cache/readme-demo/voice-1.wav');parser.add_argument('--require-improvement',action='store_true',help='Fail unless both known sources improve; required before automatic use.');args=parser.parse_args()
    a=read_audio(args.first);b=read_audio(args.second);count=min(len(a),len(b),RATE*4)
    a=a[:count]*.45;b=b[:count]*.45;mix=a+b
    session=load_separator(MODELS/MODEL_ID);began=time.monotonic();output=separate_clip(session,mix);elapsed=time.monotonic()-began
    baseline=[si_sdr(mix,x) for x in [a,b]]
    choices=[([si_sdr(output[:,permutation[i]],x) for i,x in enumerate([a,b])],permutation) for permutation in itertools.permutations(range(2))]
    scores,permutation=max(choices,key=lambda item:sum(item[0]))
    report={'synthetic_seconds':count/RATE,'inference_seconds':round(elapsed,3),'baseline_si_sdr_db':baseline,'separated_si_sdr_db':scores,'improvement_db':[scores[i]-baseline[i] for i in range(2)],'source_order':permutation,'shape':list(output.shape),'natural_audio_accuracy_claim':False}
    report['both_sources_improved']=min(report['improvement_db'])>0
    folder=Path('test-results');folder.mkdir(exist_ok=True);(folder/'separator-synthetic-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    if args.require_improvement and not report['both_sources_improved']:raise SystemExit('Both-source improvement gate failed. Automatic replacement is not justified.')
