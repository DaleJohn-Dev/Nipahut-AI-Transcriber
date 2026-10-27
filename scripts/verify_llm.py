import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.models import manager
from app.pipeline import llm_names
import httpx

if __name__ == '__main__':
    try:
        manager.load('qwen-0.6b')
        names = llm_names([{'speaker_id':'speaker_00','start':0,'end':4,'text':'Hello, my name is David.'},
                           {'speaker_id':'speaker_01','start':5,'end':8,'text':'Hi, I am Sarah.'}], 60)
        print('Verified names:', names)
        assert names['speaker_00']['name'] == 'David'
        assert names['speaker_01']['name'] == 'Sarah'
    finally:
        manager.shutdown()
