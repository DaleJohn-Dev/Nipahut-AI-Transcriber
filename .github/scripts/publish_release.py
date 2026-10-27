"""Publish source tags and the current preview release after regression succeeds."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_version import validate


def release_body(changelog,version):
    sections=re.split(r'(?m)^## ',changelog)
    section=next(s for s in sections if s.startswith(version+' — '))
    return section.split('\n',1)[1].strip()+'\n\nSource-only development preview. Model weights and user data are not included.'


def main():
    version,history=validate(ROOT)
    token=os.environ['GH_TOKEN'];repository=os.environ['GITHUB_REPOSITORY'];head=os.environ['GITHUB_SHA']
    if os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Release publication runs only from main.')
    def api(path,body=None):
        request=urllib.request.Request('https://api.github.com/repos/'+repository+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code==404 and body is None:return None
            raise RuntimeError(f'GitHub publication failed: HTTP {error.code} on {path}') from None
    for item in history:
        tag='v'+item['version'];commit=item['commit'] or head
        subprocess.run(['git','merge-base','--is-ancestor',commit,head],cwd=ROOT,check=True)
        existing=api('/git/ref/tags/'+tag)
        if existing:
            if existing['object']['type']!='commit' or existing['object']['sha']!=commit:raise ValueError('Refusing to move existing tag '+tag)
        else:api('/git/refs',{'ref':'refs/tags/'+tag,'sha':commit})
        print('Verified source tag '+tag)
    tag='v'+version
    if not api('/releases/tags/'+tag):
        release=api('/releases',{'tag_name':tag,'target_commitish':head,'name':'Nipahut AI Transcriber '+tag,
            'body':release_body((ROOT/'CHANGELOG.md').read_text(encoding='utf-8'),version),'draft':False,'prerelease':'-' in version,'make_latest':'false' if '-' in version else 'true'})
        print('Published '+release['html_url'])
    else:print('Release already exists; no changes needed.')


if __name__=='__main__':main()
