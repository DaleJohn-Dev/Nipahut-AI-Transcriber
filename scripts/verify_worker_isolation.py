"""Verify real inference leaves the parent responsive and can be cancelled."""
import sys,time,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.diarization_worker import run_native_diarization
from app.storage import write_json

if __name__=='__main__':
    beats=[];stop=threading.Event()
    def heartbeat():
        while not stop.wait(.05):beats.append(time.monotonic())
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    began=time.monotonic()
    turns=run_native_diarization('test-results/two-speaker-test.wav','diarization-campplus',2,.5,lambda p:None,lambda:None)
    inference_seconds=time.monotonic()-began
    stop.set();thread.join()
    gap=max([b-a for a,b in zip(beats,beats[1:])] or [10])
    assert gap<1,('Parent stalled',gap)
    assert len({t['speaker'] for t in turns})==2
    class TestCancellation(Exception):pass
    began=time.monotonic()
    def check():
        if time.monotonic()-began>.5:raise TestCancellation()
    try:run_native_diarization('test-results/two-speaker-test.wav','diarization-campplus',2,.5,lambda p:None,check)
    except TestCancellation:pass
    else:raise AssertionError('Cancellation was ignored')
    result={'inference_seconds':inference_seconds,'max_parent_heartbeat_gap':gap,'cancel_seconds':time.monotonic()-began,'detected_speakers':2}
    write_json(Path('test-results/worker-isolation.json'),result)
    print(result,flush=True)
