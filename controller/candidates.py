"""Offline operator catalogue. Never imported by the execution engine."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from worker.registry import load_scope_registry

LIMITS = dict(bytes=2 * 1024 * 1024, depth=64, operations=1000, ref_chain=16, ref_visits=10000, candidates=100, expanded_nodes=100000)
ID_PATTERN = '^doc-[a-z]+-[0-9]{3}$'
METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'}


class ImportFailure(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ImportFailure('DUPLICATE_KEY')
        result[key] = value
    return result


def fail_constant(_):
    raise ImportFailure('NONFINITE_NUMBER')


def local_path(path):
    if '://' in str(path) or str(path).startswith(('file:', 'data:', '//', '\\\\')):
        raise ImportFailure('LOCAL_FILE_REQUIRED')
    result = Path(path)
    if result.is_symlink() or not result.is_file():
        raise ImportFailure('REGULAR_LOCAL_FILE_REQUIRED')
    return result


def read_local(path):
    with local_path(path).open('rb') as source:
        raw = source.read(LIMITS['bytes'] + 1)
    if len(raw) > LIMITS['bytes']:
        raise ImportFailure('INPUT_SIZE_LIMIT')
    return raw


class Resolver:
    def __init__(self, root):
        self.root, self.visits = root, 0
        self.nodes = 0

    def expand(self, value, depth=0, chain=()):
        self.nodes += 1
        if self.nodes > LIMITS['expanded_nodes']:
            raise ImportFailure('EXPANSION_LIMIT')
        if depth > LIMITS['depth']:
            raise ImportFailure('DEPTH_LIMIT')
        if isinstance(value, list):
            return [self.expand(x, depth + 1, chain) for x in value]
        if not isinstance(value, dict):
            return value
        if any(k in value for k in ('allOf', 'anyOf', 'oneOf', 'not', '$dynamicRef')):
            raise ImportFailure('SCHEMA_COMPOSITION_UNSUPPORTED')
        if '$ref' in value:
            ref = value['$ref']
            if not isinstance(ref, str) or not ref.startswith('#/'):
                raise ImportFailure('NONLOCAL_REF')
            if len(value) != 1:
                raise ImportFailure('REF_SIBLINGS_UNSUPPORTED')
            if ref in chain:
                raise ImportFailure('REF_CYCLE')
            if len(chain) >= LIMITS['ref_chain']:
                raise ImportFailure('REF_CHAIN_LIMIT')
            self.visits += 1
            if self.visits > LIMITS['ref_visits']:
                raise ImportFailure('REF_VISIT_LIMIT')
            target = self.root
            for token in ref[2:].split('/'):
                if re.search(r'~(?![01])', token):
                    raise ImportFailure('INVALID_POINTER')
                token = token.replace('~1', '/').replace('~0', '~')
                if not isinstance(target, dict) or token not in target:
                    raise ImportFailure('MISSING_REF')
                target = target[token]
            return self.expand(target, depth + 1, (*chain, ref))
        # Annotation values never enter the catalogue or control analysis.
        return {k: self.expand(v, depth + 1, chain) for k, v in value.items()
                if k not in {'description', 'summary', 'example', 'examples', 'default', 'externalDocs'} and not k.startswith('x-')}


def schema_type(schema, expected):
    """Only an unambiguous, non-nullable primitive/container declaration is supported."""
    return (isinstance(schema, dict) and schema.get('type') == expected
            and schema.get('nullable', False) is False
            and (expected == 'object' or 'properties' not in schema)
            and (expected == 'array' or 'items' not in schema))


def field(schema, selector):
    for key in selector.split('.'):
        if not schema_type(schema, 'object') or not isinstance(schema.get('properties'), dict):
            return {}
        schema = schema['properties'].get(key, {})
    return schema if isinstance(schema, dict) else {}


def response_schema(operation):
    return operation.get('responses', {}).get('200', {}).get('content', {}).get('application/json', {}).get('schema', {})


def origin_check(doc, path_item, operation, origin):
    servers = operation.get('servers', path_item.get('servers', doc.get('servers')))
    if servers is None:
        return 'operator_registry', None
    if not isinstance(servers, list) or len(servers) != 1 or not isinstance(servers[0], dict):
        return 'specification', 'AMBIGUOUS_SERVERS'
    server = servers[0]
    if server.get('variables') or '{' in str(server.get('url', '')):
        return 'specification', 'SERVER_VARIABLE_UNSUPPORTED'
    if server.get('url') != origin:
        return 'specification', 'ORIGIN_MISMATCH'
    return 'specification', None


def auth_matches(doc, item, operation, adapter):
    security = operation.get('security', doc.get('security'))
    if not isinstance(security, list) or len(security) != 1 or not isinstance(security[0], dict) or len(security[0]) != 1:
        return False
    name, scopes = next(iter(security[0].items()))
    scheme = doc.get('components', {}).get('securitySchemes', {}).get(name, {})
    if scopes != []:
        return False
    return (scheme.get('type') == 'http' and scheme.get('scheme') == 'bearer') if adapter.auth_mode == 'bearer' else (
        scheme.get('type') == 'apiKey' and scheme.get('in') == 'cookie' and scheme.get('name') == adapter.cookie_name)


def anonymous_login_supported(doc, operation):
    """Login supplies no prior credentials. Validate every OR/AND branch before accepting anonymity."""
    security = operation.get('security', doc.get('security', []))
    if not isinstance(security, list):
        return False
    components = doc.get('components', {})
    schemes = components.get('securitySchemes', {}) if isinstance(components, dict) else None
    if not isinstance(schemes, dict):
        return False
    for alternative in security:
        if not isinstance(alternative, dict):
            return False
        for name, scopes in alternative.items():
            scheme = schemes.get(name)
            if scopes != [] or not isinstance(scheme, dict):
                return False
            if scheme.get('type') == 'apiKey':
                if scheme.get('in') not in ('header', 'cookie', 'query') or not isinstance(scheme.get('name'), str) or not scheme['name']:
                    return False
            elif scheme.get('type') == 'http':
                if scheme.get('scheme') not in ('basic', 'bearer'):
                    return False
            else:
                return False
    # OR is the outer array; schemes within each object are AND. Only an empty
    # requirement can be satisfied by the credential-free login transport.
    return not security or {} in security


def parameters(item, operation):
    merged = {}
    for entries in (item.get('parameters', []), operation.get('parameters', [])):
        if not isinstance(entries, list):
            raise ImportFailure('INVALID_PARAMETERS')
        seen = set()
        for entry in entries:
            key = (entry['in'], entry['name'])
            if key in seen:
                raise ImportFailure('DUPLICATE_PARAMETER')
            seen.add(key)
            merged[key] = entry
    return list(merged.values())


def supplied_inputs(item, op):
    return not op.get('requestBody') and not any(p.get('required') is True and p['in'] != 'path' for p in parameters(item, op))


def analyse(input_path, registry_path, target_id):
    try:
        return _analyse(input_path, registry_path, target_id)
    except ImportFailure:
        raise
    except Exception:
        raise ImportFailure('INVALID_INPUT_OR_REGISTRY') from None


def _analyse(input_path, registry_path, target_id):
    raw = read_local(input_path)
    parsed = json.loads(raw, object_pairs_hook=unique, parse_constant=fail_constant)
    # Inspect even ignored annotations for depth and nonfinite numeric overflow.
    stack = [(parsed, 0)]
    import math
    while stack:
        value, depth = stack.pop()
        if depth > LIMITS['depth']:
            raise ImportFailure('DEPTH_LIMIT')
        if isinstance(value, float) and not math.isfinite(value):
            raise ImportFailure('NONFINITE_NUMBER')
        if isinstance(value, (dict, list)):
            stack.extend((v, depth + 1) for v in (value.values() if isinstance(value, dict) else value))
    if not isinstance(parsed, dict) or not re.fullmatch(r'3\.[01]\.\d+', str(parsed.get('openapi'))):
        raise ImportFailure('UNSUPPORTED_VERSION')
    doc = Resolver(parsed).expand(parsed)
    paths = doc['paths']
    if not isinstance(paths, dict):
        raise ImportFailure('INVALID_PATHS')
    registry = load_scope_registry(local_path(registry_path))
    profile, adapter = registry.profile(target_id), registry.adapter(target_id)
    origin = registry.policies[target_id].base_url
    config_hash = digest(canonical({'origin': origin, 'profile': profile.normalized(), 'adapter': adapter.model_dump(mode='json')}))
    candidates, excluded, operations = [], {}, 0
    for path, item in sorted(paths.items()):
        if not isinstance(item, dict):
            raise ImportFailure('INVALID_PATH_ITEM')
        for method, op in item.items():
            if method not in METHODS:
                continue
            operations += 1
            if operations > LIMITS['operations']:
                raise ImportFailure('OPERATION_LIMIT')
            if not isinstance(op, dict):
                raise ImportFailure('INVALID_OPERATION')
            if method != 'get':
                excluded['NON_GET'] = excluded.get('NON_GET', 0) + 1
        op = item.get('get')
        if op is None:
            continue
        match = re.fullmatch(r'(/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+)/\{([A-Za-z_][A-Za-z0-9_]*)\}', path)
        if not match:
            excluded['NOT_SINGLE_FINAL_PARAMETER'] = excluded.get('NOT_SINGLE_FINAL_PARAMETER', 0) + 1
            continue
        if len(candidates) >= LIMITS['candidates']:
            raise ImportFailure('CANDIDATE_LIMIT')
        normalized = match[1] + '/{document_id}'
        source, origin_error = origin_check(doc, item, op, origin)
        reasons = []
        status = 'NEEDS_CONFIGURATION'
        if origin_error:
            reasons.append(origin_error)
            status = 'OUT_OF_SCOPE' if origin_error == 'ORIGIN_MISMATCH' else 'UNSUPPORTED'
        elif 'access-control-http' not in profile.scenarios or not {'login', 'list_own_documents', 'fetch_document'} <= set(profile.operations):
            status, reasons = 'OUT_OF_SCOPE', ['READ_FLOW_NOT_AUTHORIZED']
        else:
            if normalized != adapter.routes.detail_path:
                reasons.append('PATH_NOT_REGISTERED')
            params = parameters(item, op)
            declared = [p for p in params if p['in'] == 'path']
            if len(declared) != 1 or declared[0]['name'] != match[2] or declared[0].get('required') is not True:
                reasons.append('PATH_PARAMETER_UNPROVEN')
            elif declared[0].get('schema') != {'type': 'string', 'pattern': ID_PATTERN}:
                reasons.append('ID_FORMAT_UNPROVEN')
            if not supplied_inputs(item, op):
                reasons.append('REQUIRED_INPUT_UNSUPPORTED')
            if not auth_matches(doc, item, op, adapter):
                reasons.append('AUTH_MAPPING_UNPROVEN')
            detail = response_schema(op)
            for selector in (adapter.resource_id_field, adapter.owner_field, adapter.visibility_field, adapter.content_field, adapter.content_kind_field):
                expected_type = 'boolean' if selector == adapter.visibility_field and isinstance(adapter.private_value, bool) else 'string'
                if not schema_type(field(detail, selector), expected_type):
                    reasons.append('RESPONSE_MAPPING_UNPROVEN')
                    break
            login_item = paths.get(adapter.routes.login_path, {})
            login = login_item.get('post', {})
            listing_item = paths.get(adapter.routes.list_path, {})
            listing = listing_item.get('get', {})
            if not anonymous_login_supported(doc, login):
                reasons.append('LOGIN_AUTH_UNPROVEN')
            login_schema = login.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
            list_schema = response_schema(listing)
            array = field(list_schema, adapter.list_field)
            controls = (login and listing and field(login_schema, adapter.login_user_field) and field(login_schema, adapter.login_password_field)
                        and schema_type(array, 'array') and schema_type(array.get('items'), 'object')
                        and schema_type(field(array.get('items', {}), adapter.list_id_field), 'string')
                        and schema_type(field(array.get('items', {}), adapter.list_owner_field), 'string')
                        and schema_type(field(list_schema, adapter.list_account_field), 'string')
                        and auth_matches(doc, listing_item, listing, adapter) and supplied_inputs(listing_item, listing)
                        and not parameters(login_item, login)
                        and not origin_check(doc, login_item, login, origin)[1] and not origin_check(doc, listing_item, listing, origin)[1]
                        and {'user-a', 'user-b'} <= set(profile.scenarios['access-control-http']))
            if adapter.auth_mode == 'bearer':
                controls = controls and schema_type(field(response_schema(login), adapter.token_field), 'string')
            else:
                controls = controls and schema_type(login.get('responses', {}).get('200', {}).get('headers', {}).get('Set-Cookie', {}).get('schema', {}), 'string')
            controls = controls and set(login_schema.get('required', [])) <= {adapter.login_user_field, adapter.login_password_field}
            controls = controls and all(schema_type(field(login_schema, x), 'string') for x in (adapter.login_user_field, adapter.login_password_field))
            if not controls:
                reasons.append('CONTROLS_UNPROVEN')
            if not reasons:
                status, reasons = 'READY_FOR_REVIEW', ['REGISTERED_READ_FLOW_MATCH']
        # Only operator-approved literal paths are disclosed, never arbitrary spec paths/names.
        candidates.append(dict(candidate_id=digest(canonical({'method': 'GET', 'path': normalized, 'target': target_id})),
            finding_type='cross_account_document_access', method='GET',
            path_template=normalized if normalized == adapter.routes.detail_path else None,
            origin_source=source, adapter_id=adapter.adapter_id, status=status, reason_codes=reasons,
            verification_status='NOT_EXECUTED'))
    return dict(schema_version='1.0', source_kind='openapi_json', source_sha256=digest(raw), target_id=target_id,
                registry_sha256=config_hash, network_requests=0, model_calls=0, partial=False,
                limits=LIMITS.copy(), excluded=excluded, candidates=candidates)


def markdown(result):
    lines = ['# OpenAPI candidate review', '', 'NOT_EXECUTED. Candidate presence is not a finding or execution authorization.', '',
             '| Candidate | Path | Status | Reasons |', '|---|---|---|---|']
    for c in result['candidates']:
        lines.append(f"| {c['candidate_id']} | {c['path_template'] or '[withheld]'} | {c['status']} | {', '.join(c['reason_codes'])} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description='Offline OpenAPI candidate review; never executes candidates')
    parser.add_argument('command', choices=['import-openapi'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--target', required=True, choices=['lab-web'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        output = args.output
        summary = output.with_suffix('.md')
        if output.suffix != '.json' or output.exists() or summary.exists():
            raise ImportFailure('NEW_JSON_AND_MARKDOWN_PATHS_REQUIRED')
        result = analyse(args.input, args.registry, args.target)
        with output.open('x', encoding='utf-8') as dest:
            dest.write(json.dumps(result, indent=2) + '\n')
        with summary.open('x', encoding='utf-8') as dest:
            dest.write(markdown(result))
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({'ok': False, 'reason_code': str(exc) if isinstance(exc, ImportFailure) else 'IMPORT_OR_OUTPUT_FAILED'}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
