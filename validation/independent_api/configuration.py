"""Operator-written mapping, kept separate from the standalone server's code."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def registry_for(auth, port, budget=11):
    if auth not in ('cookie', 'bearer') or type(port) is not int or not 0 < port < 65536 or budget not in (2, 11):
        raise ValueError('invalid local configuration')
    value = json.loads((ROOT / 'registry.cookie.json').read_text(encoding='utf-8'))
    target = value['targets']['lab-web']
    target['origin'] = f'http://127.0.0.1:{port}'
    target['profile']['limits']['max_requests'] = budget
    if auth == 'bearer':
        target['adapter'].update(auth_mode='bearer', cookie_name=None, token_field='session.grant.credential')
    return value


def specification(auth):
    if auth not in ('cookie', 'bearer'):
        raise ValueError('invalid authentication')
    return json.loads((ROOT / f'openapi.{auth}.json').read_text(encoding='utf-8'))
