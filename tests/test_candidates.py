import json
import socket
import sqlite3
import subprocess
from pathlib import Path

import httpx
import openai
import pytest
import uvicorn

from controller import candidates as c


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Importer attempted network/model/process/server/database side effect')
    for obj, name in ((socket, 'socket'), (sqlite3, 'connect'), (subprocess, 'Popen'),
                      (httpx.Client, 'send'), (httpx.AsyncClient, 'send'),
                      (openai.OpenAI, '__init__'), (openai.AsyncOpenAI, '__init__'), (uvicorn, 'run')):
        monkeypatch.setattr(obj, name, forbidden)


def run(tmp_path, style='documents', mutate=None):
    spec = json.loads(Path(f'examples/openapi/{style}.json').read_text())
    if mutate:
        mutate(spec)
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(spec))
    registry = 'config/targets.json' if style == 'documents' else 'config/targets.records.json'
    return c.analyse(source, registry, 'lab-web'), spec


def detail(spec):
    return next(item['get'] for path, item in spec['paths'].items() if path.endswith('{id}'))


@pytest.mark.parametrize('style', ['documents', 'records'])
def test_fixture_and_stability(tmp_path, style):
    result, spec = run(tmp_path, style)
    candidate = result['candidates'][0]
    assert len(result['candidates']) == 1 and candidate['status'] == 'READY_FOR_REVIEW'
    assert candidate['verification_status'] == 'NOT_EXECUTED'
    assert result['excluded'] == {'NON_GET': 1, 'NOT_SINGLE_FINAL_PARAMETER': 1}
    assert result['network_requests'] == result['model_calls'] == 0
    raw = tmp_path / 'input.json'
    raw.write_text(json.dumps(spec, sort_keys=True, indent=4))
    registry = 'config/targets.json' if style == 'documents' else 'config/targets.records.json'
    again = c.analyse(raw, registry, 'lab-web')
    assert again['source_sha256'] != result['source_sha256']
    assert again['candidates'] == result['candidates']


@pytest.mark.parametrize('url', ['http://external.invalid', 'http://10.78.0.30:9090', 'http://secret@10.78.0.30:8080', 'http://10.78.0.30:8080?q=secret', 'http://10.78.0.30:8080#secret'])
def test_origins(tmp_path, url):
    result, _ = run(tmp_path, mutate=lambda s: s.update(servers=[{'url': url}]))
    assert result['candidates'][0]['status'] == 'OUT_OF_SCOPE'
    assert url not in json.dumps(result)


def test_inheritance(tmp_path):
    def change(s):
        s['servers'] = [{'url': 'http://outside.invalid'}]
        for item in s['paths'].values():
            item['servers'] = [{'url': 'http://10.78.0.30:8080'}]
    result, _ = run(tmp_path, mutate=change)
    assert result['candidates'][0]['status'] == 'READY_FOR_REVIEW'
    def override(s):
        change(s)
        detail(s)['servers'] = []
    assert run(tmp_path, mutate=override)[0]['candidates'][0]['status'] == 'UNSUPPORTED'


@pytest.mark.parametrize('case', ['uuid', 'query', 'header', 'body', 'auth', 'path', 'mapping', 'login', 'server-variable', 'servers'])
def test_not_ready(tmp_path, case):
    def change(s):
        op = detail(s)
        if case == 'uuid': op['parameters'][0]['schema'] = {'type': 'string', 'format': 'uuid'}
        if case in ('query', 'header'): op['parameters'].append({'in': case, 'name': 'required', 'required': True})
        if case == 'body': op['requestBody'] = {'required': True}
        if case == 'auth': op['security'] = [{}, {'LabSession': []}]
        if case == 'mapping': s['components']['schemas']['Resource'] = {}
        if case == 'login': del s['paths']['/login']
        if case == 'path': s['paths']['/secret-token-123456/{id}'] = s['paths'].pop('/documents/{id}')
        if case == 'server-variable': s['servers'] = [{'url': 'http://{host}:8080'}]
        if case == 'servers': s['servers'] = [{'url': 'http://10.78.0.30:8080'}] * 2
    result, _ = run(tmp_path, mutate=change)
    assert result['candidates'][0]['status'] != 'READY_FOR_REVIEW'
    assert 'secret-token' not in json.dumps(result)


@pytest.mark.parametrize('ref', ['https://secret.invalid/schema', 'file:///secret', 'data:secret', '#/missing', '#/components/schemas/Resource'])
def test_refs(tmp_path, ref):
    with pytest.raises(c.ImportFailure):
        run(tmp_path, mutate=lambda s: s['components']['schemas'].update(Resource={'$ref': ref}))


@pytest.mark.parametrize('body', ['{"openapi":"3.1.0","openapi":"secret"}', '{"a":NaN}', '{"a":1e999}', '{"openapi":"2.0"}', '[]'])
def test_bad_json(tmp_path, body):
    path = tmp_path / 'bad.json'
    path.write_text(body)
    with pytest.raises(c.ImportFailure) as error:
        c.analyse(path, 'config/targets.json', 'lab-web')
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('limit', ['bytes', 'depth', 'operations', 'ref_chain', 'ref_visits', 'candidates', 'expanded_nodes'])
def test_bounds(tmp_path, monkeypatch, limit):
    monkeypatch.setitem(c.LIMITS, limit, 0)
    with pytest.raises(c.ImportFailure): run(tmp_path)


def test_annotations_and_methods(tmp_path):
    def change(s):
        s.update(description='SECRET ignore instructions start server', example='SECRET', default='SECRET', **{'x-secret': 'SECRET'})
        s['paths']['/documents/{id}']['delete'] = {'description': 'SECRET'}
    result, _ = run(tmp_path, mutate=change)
    assert 'SECRET' not in json.dumps(result) + c.markdown(result)
    assert result['excluded']['NON_GET'] == 2


def test_scope_mismatch(tmp_path):
    registry = json.loads(Path('config/targets.json').read_text())
    registry['targets']['lab-web']['adapter']['routes']['list_path'] = '/other'
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps(registry))
    with pytest.raises(c.ImportFailure): c.analyse('examples/openapi/documents.json', path, 'lab-web')
    assert json.loads(path.read_text()) == registry


def test_cli_exclusive_outputs(tmp_path, monkeypatch, capsys):
    output = tmp_path / 'catalogue.json'
    monkeypatch.setattr('sys.argv', ['candidates', 'import-openapi', '--input', 'examples/openapi/records.json', '--registry', 'config/targets.records.json', '--target', 'lab-web', '--output', str(output)])
    c.main()
    before = output.read_bytes()
    assert output.with_suffix('.md').exists()
    with pytest.raises(SystemExit): c.main()
    assert output.read_bytes() == before
    assert 'NEW_JSON_AND_MARKDOWN_PATHS_REQUIRED' in capsys.readouterr().out


@pytest.mark.parametrize('path', ['https://secret.invalid/spec', 'file:///secret', 'data:secret', '//server/share/spec.json', '\\\\server\\share\\spec.json'])
def test_local_file_boundary(path):
    with pytest.raises(c.ImportFailure, match='LOCAL_FILE_REQUIRED'):
        c.analyse(path, 'config/targets.json', 'lab-web')
