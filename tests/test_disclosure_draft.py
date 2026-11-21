"""Authenticated offline review of copies of the published synthetic runs."""
from collections import Counter
import json
from pathlib import Path
import secrets
import shutil

from fastapi.testclient import TestClient
import pytest

from controller import workspace
from controller.api import AppSettings, create_app


ARCHIVES = Path('reports/independent_api_validation_20261113')
ORIGIN = 'http://testserver'


def copy_run(root, case='cookie-vulnerable-function-normal'):
    source, = (ARCHIVES / case / 'runs').iterdir()
    return Path(shutil.copytree(source, root / 'runs' / source.name))


def make_app(root, token):
    service = workspace.Workspace(profiles={}, state_path=root / 'state', reports_path=root / 'runs',
                                  policy_client=None, client_factory=None)
    settings = AppSettings(database_path=root / 'test.db', reports_path=root / 'runs',
                           session_secret=secrets.token_hex(32), access_token=token,
                           allowed_origins=frozenset({ORIGIN}), allowed_hosts=frozenset({'testserver'}),
                           allowed_clients=frozenset({'testclient', '127.0.0.1'}))
    return create_app(settings=settings, clients={}, workspace=service)


@pytest.fixture
def owner(tmp_path):
    token = secrets.token_urlsafe(32)
    with TestClient(make_app(tmp_path, token), base_url=ORIGIN) as client:
        session = client.post('/api/session', headers={'origin': ORIGIN}, json={'access_token': token})
        assert session.status_code == 200
        client.headers.update({'origin': ORIGIN, 'x-csrf-token': session.json()['csrf_token']})
        yield client


def url(folder):
    return f'/api/operator/runs/{folder.name}/disclosure-draft'


def confirmation(digest):
    return {'confirmed': True, 'review_digest': digest}


def test_reviewed_download(tmp_path, owner, monkeypatch):
    folder = copy_run(tmp_path)
    report = folder / 'report.json'
    private = secrets.token_urlsafe(32)
    report.write_text(json.dumps({**json.loads(report.read_bytes()), 'private_test_field': private}))
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    review = owner.get(url(folder)).json()
    evidence = json.loads(before['evidence.json'])
    read = workspace.read_local
    counts = Counter()

    def counted(path):
        if path.parent == folder:
            counts[path.name] += 1
        return read(path)

    monkeypatch.setattr(workspace, 'read_local', counted)
    issued = owner.post(url(folder), json=confirmation(review['review_digest']))
    assert issued.status_code == 200 and issued.text == review['markdown']
    assert counts == {name: 1 for name in before if name.endswith('.json')}
    assert folder.name in issued.text and folder.name in issued.headers['content-disposition']
    assert '로컬 합성 사례 · 제출 전 검토용' in issued.text
    assert evidence[6]['evidence_id'] in issued.text and evidence[5]['evidence_id'] in issued.text
    for value in (private, evidence[6]['proof_digest'], evidence[6]['session_binding']):
        assert value not in issued.text and value not in str(review)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


@pytest.mark.parametrize(('fault', 'reason'), [
    ('fixed', 'DRAFT_BLOCKED'), ('incomplete', 'DRAFT_NOT_COMPLETED'),
    ('missing_row', 'DRAFT_UNCONFIRMED'), ('disagreement', 'DRAFT_UNCONFIRMED'),
    ('inconclusive', 'DRAFT_UNCONFIRMED'),
    ('unreadable', 'SAVED_INPUT_UNREADABLE'),
])
def test_ineligible(tmp_path, owner, fault, reason):
    folder = copy_run(tmp_path, 'cookie-fixed-function-normal' if fault == 'fixed'
                      else 'cookie-vulnerable-function-normal')
    if fault in ('missing_row', 'unreadable'):
        file = folder / 'evidence.json'
        file.write_text(json.dumps(json.loads(file.read_bytes())[:-1]) if fault == 'missing_row' else '{')
    elif fault in ('incomplete', 'disagreement', 'inconclusive'):
        file = folder / 'report.json'
        changes = {'status': 'FAILED'} if fault == 'incomplete' else {'verdict': 'INCONCLUSIVE'}
        file.write_text(json.dumps({**json.loads(file.read_bytes()), **changes}))
        if fault == 'inconclusive':
            evidence = folder / 'evidence.json'
            rows = json.loads(evidence.read_bytes())
            rows[6]['status_code'] = 503
            evidence.write_text(json.dumps(rows))
    for response in (owner.get(url(folder)), owner.post(url(folder), json=confirmation('0' * 64))):
        assert response.status_code == 409 and response.json()['detail']['code'] == reason
        assert 'content-disposition' not in response.headers


def test_new_inputs_require_review_even_when_conclusion_stays_vulnerable(tmp_path, owner):
    folder = copy_run(tmp_path)
    other = copy_run(tmp_path, 'cookie-vulnerable-mcp-normal')
    payload = confirmation(owner.get(url(folder)).json()['review_digest'])
    file = folder / 'evidence.json'
    rows = json.loads(file.read_bytes())
    rows[6]['request_id'] = 'updated-request-reference'
    file.write_text(json.dumps(rows))
    for run in (folder, other):
        response = owner.post(url(run), json=payload)
        assert response.status_code == 409 and response.json()['detail']['code'] == 'DRAFT_REVIEW_CHANGED'
    fresh = owner.get(url(folder)).json()
    assert owner.post(url(folder), json=confirmation(fresh['review_digest'])).text == fresh['markdown']
    file.write_text(json.dumps(rows[:-1]))
    assert owner.post(url(folder), json=confirmation(fresh['review_digest'])).json()['detail']['code'] == 'DRAFT_UNCONFIRMED'


def test_template_update_invalidates_review(tmp_path, owner, monkeypatch):
    from controller import disclosure_draft

    folder = copy_run(tmp_path)
    payload = confirmation(owner.get(url(folder)).json()['review_digest'])
    monkeypatch.setattr(disclosure_draft, 'TEMPLATE', 'different-template-version')
    assert owner.post(url(folder), json=payload).json()['detail']['code'] == 'DRAFT_REVIEW_CHANGED'


def test_session_csrf_and_confirmation(tmp_path):
    folder = copy_run(tmp_path)
    token = secrets.token_urlsafe(32)
    with TestClient(make_app(tmp_path, token), base_url=ORIGIN, headers={'origin': ORIGIN}) as client:
        payload = confirmation('0' * 64)
        assert client.get(url(folder)).status_code == 401
        assert client.post(url(folder), json=payload).status_code == 401
        login = client.post('/api/session', json={'access_token': token})
        payload = confirmation(client.get(url(folder)).json()['review_digest'])
        assert client.post(url(folder), json=payload).status_code == 403
        client.headers['x-csrf-token'] = login.json()['csrf_token']
        assert client.post(url(folder), json=payload, headers={'origin': 'https://invalid.test'}).status_code == 403
        for invalid in ({**payload, 'confirmed': False}, {'review_digest': payload['review_digest']},
                        {**payload, 'markdown': 'replacement'}):
            assert client.post(url(folder), json=invalid).status_code == 422
