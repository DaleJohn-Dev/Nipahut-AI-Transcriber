"""Isolate long native inference so it cannot hold the desktop/server GIL."""
import multiprocessing as mp
import queue
import time
import traceback
import sys

def _worker(audio_path, model_id, count, threshold, events, silenced_ranges, use_profiles=True, use_classifier=True):
    if sys.stdout is None or sys.stderr is None:
        from .storage import DATA
        log = (DATA/'speaker-worker.log').open('w',encoding='utf-8',buffering=1)
        sys.stdout = sys.stderr = log
    from .models import manager
    from .audio import read_audio
    import sherpa_onnx as so
    try:
        manager.load(model_id)
        model=manager.loaded[model_id]
        config=manager.diarization_configs[model_id]
        config.clustering=so.FastClusteringConfig(num_clusters=count or -1,threshold=threshold,compute_confidence=True)
        model.set_config(config)
        previous=[-1]
        def progress(done,total):
            percent=int(done/max(1,total)*100)
            if percent!=previous[0]:
                previous[0]=percent
                events.put(('progress',.75*done/max(1,total)))
            # Allow the queue feeder to flush while the native call holds its GIL.
            time.sleep(.001)
            return 0
        from .audio_edits import apply_silences
        waveform=apply_silences(read_audio(audio_path),silenced_ranges)
        result=model.process(waveform,callback=progress).sort_by_start_time()
        native=[{'start':t.start,'end':t.end,'speaker':t.speaker} for t in result]
        if not use_classifier:
            if len({t['speaker'] for t in native})>32:
                raise RuntimeError('Automatic clustering produced more than 32 groups. Enable recording-wide voice matching or review the participant count; this result was rejected.')
            events.put(('result',native))
            return
        from .voice_classifier import classify
        from .voice_profiles import extractor, available
        turns, diagnostics=classify(waveform,native,extractor(model_id),count,threshold,
            available(model_id) if use_profiles else (),
            lambda p: events.put(('progress',.75+.25*p)))
        events.put(('result',{'turns':turns,'classification':diagnostics}))
    except Exception as exc:
        events.put(('error',str(exc)))
        traceback.print_exc()
    finally:
        manager.shutdown()

def run_native_diarization(audio_path, model_id, count, threshold, progress, check, silenced_ranges=None, use_profiles=True, use_classifier=True):
    context=mp.get_context('spawn')
    events=context.Queue()
    process=context.Process(target=_worker,args=(str(audio_path),model_id,count,threshold,events,silenced_ranges or [],use_profiles,use_classifier),daemon=True)
    process.start()
    exited=None
    try:
        while True:
            check()
            try:
                kind,value=events.get(timeout=.15)
            except queue.Empty:
                if not process.is_alive():
                    exited=exited or time.monotonic()
                    if time.monotonic()-exited>1:
                        raise RuntimeError(f'Speaker inference worker stopped unexpectedly (exit {process.exitcode}). Original audio is retained.')
                continue
            if kind=='progress':progress(value)
            elif kind=='result':return value
            elif kind=='error':raise RuntimeError('Speaker inference: '+value)
    finally:
        if process.is_alive():
            process.join(2)
        if process.is_alive():
            process.terminate()
            process.join(3)
        if process.is_alive():
            process.kill()
            process.join()
        events.close()
        process.close()
