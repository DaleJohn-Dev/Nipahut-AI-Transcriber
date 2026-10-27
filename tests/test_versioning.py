import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from scripts import check_version

ROOT=Path(__file__).resolve().parents[1]


def copied_metadata(tmp_path):
    (tmp_path/'docs').mkdir()
    for name in ['VERSION','CHANGELOG.md','docs/version-history.json']:
        shutil.copy2(ROOT/name,tmp_path/name)
    return tmp_path


def test_current_version_matches_changelog_and_unique_source_history():
    version,history=check_version.validate(ROOT)
    assert history[-1]['version']==version and history[-1]['commit'] is None
    assert all(item['commit'] for item in history[:-1])
    assert check_version.version_key('0.2.0-preview.10')>check_version.version_key('0.2.0-preview.9')
    assert check_version.version_key('0.2.0')>check_version.version_key('0.2.0-preview.99')


def test_duplicate_or_missing_history_is_rejected(tmp_path):
    root=copied_metadata(tmp_path)
    history=json.loads((root/'docs/version-history.json').read_text(encoding='utf-8'))
    history[-2]['version']=history[-1]['version']
    (root/'docs/version-history.json').write_text(json.dumps(history))
    with pytest.raises(ValueError):check_version.validate(root)


def test_published_updates_require_a_new_version(monkeypatch,tmp_path):
    root=copied_metadata(tmp_path)
    monkeypatch.setattr(check_version.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=(root/'VERSION').read_text(encoding='utf-8')))
    with pytest.raises(ValueError,match='bump VERSION'):check_version.validate(root,'a'*40)


def test_version_resource_is_shared_by_api_and_application():
    from app.version import APP_VERSION
    from app.server import state
    assert APP_VERSION==(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    assert state()['version']==APP_VERSION


def test_bump_pins_previous_source_and_adds_new_version(monkeypatch,tmp_path):
    import runpy
    root=copied_metadata(tmp_path)
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    helper=runpy.run_path(str(ROOT/'scripts/bump_version.py'),run_name='version_helper_test')
    monkeypatch.setattr(helper['subprocess'],'check_output',lambda *a,**k:'a'*40+'\n')
    major,minor,patch,stable,preview=check_version.version_key((root/'VERSION').read_text(encoding='utf-8').strip())
    future=f'{major}.{minor}.{patch+(1 if stable else 0)}-preview.{preview+1 if not stable else 1}'
    helper['bump'](root,future,'A future documented update.','2026-10-28')
    version,history=check_version.validate(root)
    assert version==future and history[-2]['commit']=='a'*40
    assert history[-1]['commit'] is None and 'A future documented update.' in (root/'CHANGELOG.md').read_text(encoding='utf-8')


def test_release_notes_use_only_the_matching_changelog_section(monkeypatch):
    import runpy
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    helper=runpy.run_path(str(ROOT/'.github/scripts/publish_release.py'),run_name='release_helper_test')
    notes=helper['release_body']((ROOT/'CHANGELOG.md').read_text(encoding='utf-8'),'0.2.0-preview.8')
    assert 'Refresh GitHub screenshots' in notes and '0.2.0-preview.7' not in notes
    assert 'Model weights and user data are not included' in notes


def test_publisher_creates_only_the_current_commit_tag(monkeypatch):
    import io
    import runpy
    import urllib.error
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    helper=runpy.run_path(str(ROOT/'.github/scripts/publish_release.py'),run_name='publisher_test')
    monkeypatch.setenv('GH_TOKEN','test-token-only');monkeypatch.setenv('GITHUB_REPOSITORY','example/repository')
    monkeypatch.setenv('GITHUB_SHA','f'*40);monkeypatch.setenv('GITHUB_REF','refs/heads/main')
    monkeypatch.setattr(helper['subprocess'],'run',lambda *a,**k:None)
    writes=[]
    def request(req,**kwargs):
        if req.get_method()=='GET':raise urllib.error.HTTPError(req.full_url,404,'Not found',{},None)
        body=json.loads(req.data);writes.append((req.full_url,body))
        if req.full_url.endswith('/git/refs'):
            assert body['sha']=='f'*40,'Historical commits must not require broader workflow-token access'
            return io.BytesIO(b'{}')
        return io.BytesIO(b'{"html_url":"https://example.invalid/release"}')
    monkeypatch.setattr(helper['urllib'].request,'urlopen',request)
    helper['main']()
    tags=[body for url,body in writes if url.endswith('/git/refs')]
    assert len(tags)==1 and tags[0]['ref']=='refs/tags/v'+(ROOT/'VERSION').read_text(encoding='utf-8').strip()
