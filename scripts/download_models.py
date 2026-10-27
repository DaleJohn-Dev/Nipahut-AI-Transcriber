"""Explicit setup downloads. No cache duplicates; no models downloaded during inference."""
import sys
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.models import manager, CATALOG

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Install local models from Hugging Face and official upstream releases. Existing installations are reused.')
    parser.add_argument('models',nargs='*',help='Model IDs; defaults to Whisper small, CAM++ and the independent ERes2Net verifier.')
    parser.add_argument('--plan',action='store_true',help='Show sources and approximate sizes without downloading.')
    args=parser.parse_args()
    selected=args.models or ['whisper-small','diarization-campplus','diarization-eres2net']
    if any(mid not in CATALOG for mid in selected):parser.error('Unknown model ID. Options: '+', '.join(CATALOG))
    expanded=[]
    for mid in selected:
        required=CATALOG[mid].get('requires')
        for item in ([required] if required else [])+[mid]:
            if item not in expanded:expanded.append(item)
    for mid in expanded:
        spec=CATALOG[mid]
        installed=mid=='rules' or (manager.state()[list(CATALOG).index(mid)]['installed'])
        print(f'{mid}: ~{spec["size"]/1024**2:.0f} MiB | {spec["license"]} | {"installed; reusing" if installed else spec["source"]}',flush=True)
        if args.plan or installed:continue
        last = [-1]
        def report(p, message):
            tick = int(p * 100)
            if tick != last[0]:
                print(f'{tick:3d}% {message}', flush=True)
                last[0] = tick
        manager.download(mid, report)
        print(mid, 'ready', flush=True)
