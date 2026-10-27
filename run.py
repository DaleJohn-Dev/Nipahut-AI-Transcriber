"""Run the local app at http://127.0.0.1:8765. No internet required after setup."""
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['OMP_NUM_THREADS'] = '4'
if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app.server:app', host='127.0.0.1', port=8765, log_level='info', access_log=False)
