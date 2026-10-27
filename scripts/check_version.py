"""Validate the current version, changelog and immutable source-history map."""
import json
import os
from pathlib import Path
import re
import subprocess

PATTERN=re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-preview\.([1-9]\d*))?')


def version_key(value):
    match=PATTERN.fullmatch(value)
    if not match:raise ValueError('Use MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-preview.N.')
    major,minor,patch,preview=match.groups()
    return (int(major),int(minor),int(patch),preview is None,int(preview or 0))


def validate(root,base=None):
    root=Path(root)
    version=(root/'VERSION').read_text(encoding='utf-8').strip();version_key(version)
    history=json.loads((root/'docs/version-history.json').read_text(encoding='utf-8'))
    if not history or history[-1]['version']!=version or history[-1]['commit'] is not None:
        raise ValueError('The last history entry must match VERSION and use commit: null for this source revision.')
    seen=set();previous=None
    for index,item in enumerate(history):
        value=item['version'];key=version_key(value)
        if value in seen or (previous and key<=previous):raise ValueError('History versions must be unique and increasing.')
        if not item.get('summary') or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',item.get('date','')):raise ValueError('Each version needs a dated summary.')
        if index<len(history)-1 and not re.fullmatch(r'[a-f0-9]{40}',item.get('commit') or ''):raise ValueError('Past versions must identify an exact commit.')
        seen.add(value);previous=key
    changelog=(root/'CHANGELOG.md').read_text(encoding='utf-8')
    for item in history:
        if not re.search(r'^## '+re.escape(item['version'])+r' — '+re.escape(item['date'])+r'$',changelog,re.M):raise ValueError('Changelog is missing version '+item['version'])
    if base and base!='0'*40:
        if not re.fullmatch(r'[a-f0-9]{40}',base):raise ValueError('Version comparison base must be a full commit SHA.')
        previous_file=subprocess.run(['git','show',base+':VERSION'],cwd=root,text=True,capture_output=True)
        if previous_file.returncode==0 and version_key(version)<=version_key(previous_file.stdout.strip()):
            raise ValueError('Every published update must bump VERSION and add a changelog/history entry.')
    return version,history


if __name__=='__main__':
    version,history=validate(Path(__file__).resolve().parents[1],os.environ.get('VERSION_BASE_SHA'))
    print(f'PASS: v{version}, {len(history)} source versions tracked.')
