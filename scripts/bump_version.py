"""Prepare the next version while pinning the previous release to its source commit."""
import argparse
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import subprocess
from check_version import validate,version_key


def bump(root,new_version,summary,date):
    root=Path(root);old,history=validate(root)
    if version_key(new_version)<=version_key(old):raise ValueError('Choose a version newer than '+old)
    if not summary.strip():raise ValueError('Provide a concrete change summary.')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    history[-1]['commit']=commit
    history.append({'version':new_version,'date':date,'commit':None,'summary':summary.strip(),'retrospective':False})
    changelog=(root/'CHANGELOG.md').read_text(encoding='utf-8')
    marker='\n## '+old+' — '
    if marker not in changelog:raise ValueError('Cannot locate the previous changelog section.')
    before,after=changelog.split(marker,1)
    updated=before+f'\n## {new_version} — {date}\n\n{summary.strip()}\n\n## '+old+' — '+after
    (root/'VERSION').write_text(new_version+'\n',encoding='utf-8',newline='\n')
    (root/'docs/version-history.json').write_text(json.dumps(history,indent=2)+'\n',encoding='utf-8',newline='\n')
    (root/'CHANGELOG.md').write_text(updated,encoding='utf-8',newline='\n')
    validate(root)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version');parser.add_argument('--summary',required=True)
    args=parser.parse_args()
    bump(Path(__file__).resolve().parents[1],args.version,args.summary,datetime.now(timezone(timedelta(hours=8),name='Asia/Taipei')).date().isoformat())
    print('Updated VERSION, CHANGELOG.md and docs/version-history.json. Review and run checks before publishing.')
