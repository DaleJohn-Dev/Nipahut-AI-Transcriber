"""Check staged publication files without reading or printing private local data."""
import re
import subprocess
from pathlib import PurePosixPath

blocked={'data','models','output','test-results','.cache','.venv','_internal','.desktop-build'}
files=subprocess.check_output(['git','ls-files','--cached','-z']).decode('utf-8').split('\0')
failures=[]
total=0
for name in filter(None,files):
    path=PurePosixPath(name)
    if path.parts[0] in blocked and name not in {'data/.gitkeep','models/.gitkeep'}:
        failures.append((name,'local data or generated files'))
    if path.name.startswith(('RESUME_','.env')) or path.suffix.lower() in {'.wav','.mp3','.aac','.m4a','.flac','.gguf','.onnx','.exe','.dll','.pyc','.log','.pid'}:
        failures.append((name,'private/runtime file type'))
    content=subprocess.check_output(['git','show',':'+name])
    total+=len(content)
    if len(content)>20*1024**2:failures.append((name,'unexpected large source asset'))
    if path.suffix.lower() in {'.py','.ps1','.md','.json','.js','.txt','.cjs','.yml','.yaml'}:
        text=content.decode('utf-8',errors='replace')
        patterns=[r'gh[pousr]_[A-Za-z0-9]{25,}',r'github_pat_[A-Za-z0-9_]{30,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'AKIA[0-9A-Z]{16}']
        if any(re.search(pattern,text) for pattern in patterns):failures.append((name,'possible credential; inspect locally'))
if failures:
    for name,reason in failures:print(f'BLOCKED {name}: {reason}')
    raise SystemExit(1)
print(f'PASS: {len(list(filter(None,files)))} staged files, {total/1024**2:.2f} MiB; no local data, model weights or detected credentials.')
