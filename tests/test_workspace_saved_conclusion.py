"""Offline projections of archived, synthetic runs through the workspace API."""
from pathlib import Path
import json
import shutil

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from controller.workspace import Workspace
from controller.workspace_api import attach_workspace
from verifier.operator import replay

BASE = Path('reports/independent_api_validation_20261113')
VERDICTS = {'vulnerable': 'VULNERABLE', 'fixed': 'BLOCKED_BY_ACCESS_CONTROL'}


def archive(tmp_path, mode):
    source, = (BASE / f'cookie-{mode}-function-normal' / 'runs').iterdir()
    folder = tmp_path / 'runs' / source.name
    shutil.copytree(source, folder)
    ws = Workspace(profiles={}, state_path=tmp_path / 'state', reports_path=folder.parent,
                   policy_client=None, client_factory=None)
    app = FastAPI()
    attach_workspace(app, ws, lambda: 'owner', lambda: 'owner')
    return folder, TestClient(app)


def contents(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


@pytest.mark.parametrize('mode', VERDICTS)
@pytest.mark.parametrize('change', ['none', 'truncate', 'flip'])
def test_saved_conclusion(tmp_path, mode, change):
    folder, client = archive(tmp_path, mode)
    original = VERDICTS[mode]
    if change == 'truncate':
        path = folder / 'evidence.json'
        path.write_text(json.dumps(json.loads(path.read_bytes())[:-1]))
    if change == 'flip':
        path = folder / 'report.json'
        report = json.loads(path.read_bytes())
        original = next(v for v in VERDICTS.values() if v != original)
        report['verdict'] = original
        path.write_text(json.dumps(report))
    before = contents(folder)
    url = '/api/operator/runs/' + folder.name
    with client:
        row, = client.get('/api/operator/runs').json()['runs']
        view = client.get(url).json()
        data = client.get(url + '/download/json').json()
        md = client.get(url + '/download/markdown').text
        for kind in ('json', 'markdown'):
            assert client.get(url + '/download/' + kind).content == client.get(url + '/download/' + kind).content
    assert view['replay'] == replay(folder)
    assert contents(folder) == before
    assert view['version']['commit'] == 'not-recorded'
    assert view['status'] == 'COMPLETED' and row['verdict'] == data['verdict'] == original
    assert view['replay']['verdict'] == ('INCONCLUSIVE' if change == 'truncate' else VERDICTS[mode])
    if change == 'truncate':
        assert view['replay']['reason_code'] == 'REPORT_CONTRACT_MISMATCH'
    if change != 'none':
        assert '판정 보류 / 증거 불일치' in data['impact'], data['impact']
    conclusion = view['conclusion']
    assert row['conclusion'] == data['conclusion'] == conclusion
    assert conclusion['verdict'] == (original if change == 'none' else 'INCONCLUSIVE')
    assert conclusion['label'] in md.split('## 2.')[0]
    if change != 'none':
        assert conclusion['reason_code'] in md.split('## 2.')[0]
        assert conclusion['label'] in data['recommendation']
        assert conclusion['reason_code'] in data['impact'] and conclusion['reason_code'] in data['recommendation']
        assert original not in md.split('## 2.')[0]
        assert '최초 판정(이력)' in md


@pytest.mark.parametrize(('name','fault'), [('evidence.json','missing'), ('verification_contract.json','invalid'), ('evidence.json','denied')])
def test_unreadable_input(tmp_path, name, fault, monkeypatch):
    folder, client = archive(tmp_path, 'fixed')
    path = folder / name
    if fault == 'missing':
        path.unlink()
    elif fault == 'invalid':
        path.write_text('private-file-detail')
    else:
        from controller import workspace
        read = workspace.read_local
        def deny_input(file):
            if file == path:
                raise PermissionError('private-file-detail')
            return read(file)
        monkeypatch.setattr(workspace, 'read_local', deny_input)
    before = contents(folder)
    url = '/api/operator/runs/' + folder.name
    with client:
        row, = client.get('/api/operator/runs').json()['runs']
        assert row['conclusion']['state'] == 'unavailable'
        for suffix in ('', '/download/markdown', '/download/json'):
            result = client.get(url + suffix)
            assert result.status_code == 409
            assert result.json()['detail']['code'] == row['conclusion']['reason_code']
            assert 'private-file-detail' not in result.text and str(tmp_path) not in result.text
    assert contents(folder) == before


def test_missing_report_is_a_sanitized_error(tmp_path):
    folder, client = archive(tmp_path, 'vulnerable')
    (folder / 'report.json').unlink()
    before = contents(folder)
    with client:
        for suffix in ('', '/download/json', '/download/markdown'):
            result = client.get('/api/operator/runs/' + folder.name + suffix)
            assert result.status_code == 409
            assert result.json()['detail']['code'] == 'SAVED_INPUT_UNREADABLE'
        assert client.get('/api/operator/runs').json()['runs'] == []
    assert contents(folder) == before
