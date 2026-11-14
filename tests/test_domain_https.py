import asyncio
import json
from pathlib import Path
import socket

import httpcore
import httpx
import pytest
from pydantic import ValidationError

from common.domain_contract import DomainNetworkPolicy, address, hostname
from controller.candidate_execution import plan_hash
from controller.operator_execution import parse_plan
from scripts import run_domain_https_verification as harness
from validation.domain_https import HOST, TestResolver, forbid_hostname_lookup
from validation.independent_api.api import AttachmentService, attachment_server
from validation.local_https import certificates
from verifier.operator import replay
from worker.domain_transport import DomainTransport, PinnedBackend, SystemResolver, checked_answers, verify_peer
from worker.limits import WorkerLimits
from worker.operator_app import StepRequest
from worker.policy import TargetPolicy, PolicyViolation
from worker.registry import load_scope_registry
from worker.scope import ScopeViolation
from worker.tls import bind_registry_tls, load_trust


@pytest.mark.parametrize('auth,vulnerable,transport,case', harness.CASES)
def test_domain_real_tcp_matrix(tmp_path, auth, vulnerable, transport, case):
    row = harness.run_case(tmp_path, auth, vulnerable, transport, case)
    assert row['passed'], row
    assert row['temporary_key_directory_removed']
    assert row['actual_scope']['tls']['verification'] == 'dedicated-ca-dns-san-v1'
    assert not any(row['preview'].values())
    assert row['replay']['verdict_matches']


@pytest.mark.parametrize('bad', ['localhost', 'a..test', 'a.test.', '*.test', '-a.test', 'a-.test',
    'a_b.test', 'a/evil.test', 'a%2e.test', 'a@test', 'é.test', 'xn--a.test', 'a.xn--test',
    '127.1', '0177.0.0.1', '2130706433', '0x7f.0x1', 'a.123', 'a.'+'b'*64, 'a.'*127+'test'])
def test_hostname_rejects_ambiguous_or_unsupported_names(bad):
    with pytest.raises(ValueError):
        hostname(bad)


def network(ranges=('127.0.0.1',), non_global=True):
    return DomainNetworkPolicy(allowed_ip_ranges=list(ranges), allow_non_global=non_global)


def test_origin_and_normalization_boundaries(tmp_path):
    assert hostname('Attachments.SecurityAI.Test') == HOST
    one = network(['127.0.0.0/30', '127.0.0.1', '127.0.0.2/32'])
    two = network(['127.0.0.3', '127.0.0.2', '127.0.0.1', '127.0.0.0'])
    assert one == two
    a = harness.domain_config('cookie', 443)
    a['targets']['lab-web']['origin'] = 'https://Attachments.SecurityAI.Test:443'
    a['targets']['lab-web']['network'] = one.model_dump(mode='json')
    path = tmp_path/'scope.json'
    harness.write_json(path, a)
    first = load_scope_registry(path)
    a['targets']['lab-web']['origin'] = f'https://{HOST}:443'
    a['targets']['lab-web']['network'] = two.model_dump(mode='json')
    harness.write_json(path, a)
    second = load_scope_registry(path)
    assert first.config_digest('lab-web') == second.config_digest('lab-web')
    assert first.policies == second.policies
    bad = [f'http://{HOST}:443', f'https://{HOST}.:443', f'https://{HOST}:443/',
           f'https://u@{HOST}:443', f'https://{HOST}:443?', f'https://{HOST}:443#',
           f'https://{HOST}:0', f'https://{HOST}', 'https://[::ffff:127.0.0.1]:443',
           'https://[fe80::1%251]:443', 'https://127.0.0.1:443']
    for origin in bad:
        with pytest.raises(ValueError):
            TargetPolicy.from_origin('lab-web', origin, one)
    for scheme in ('http', 'https'):
        with pytest.raises(PolicyViolation):
            TargetPolicy('lab-web', scheme, '::ffff:127.0.0.1', 443)
        with pytest.raises(PolicyViolation):
            TargetPolicy('lab-web', scheme, 'fe80::1%1', 443)
    with pytest.raises(PolicyViolation):
        TargetPolicy('lab-web','https',HOST,443)  # Domain alone is never authority.


@pytest.mark.parametrize('ranges', [[], ['0.0.0.0/0'], ['::/0'], ['0.0.0.0/1','128.0.0.0/1'],
    ['::ffff:127.0.0.1'], ['fe80::1%1'], ['127.1'], ['127.0.0.1/33']])
def test_bad_networks(ranges):
    with pytest.raises(ValueError):
        network(ranges)


@pytest.mark.parametrize('value,ranges,non_global,allowed', [
    ('127.0.0.1',['127.0.0.0/8'],False,False), ('127.0.0.1',['127.0.0.1'],True,True),
    ('127.0.0.2',['127.0.0.1'],True,False), ('10.1.2.3',['10.0.0.0/8'],False,False),
    ('10.1.2.3',['10.0.0.0/8'],True,True), ('169.254.0.1',['169.254.0.0/16'],False,False),
    ('169.254.0.1',['169.254.0.0/16'],True,True), ('::1',['::1/128'],True,True),
    ('::1',['::1/128'],False,False), ('fd12::1',['fd12::/32'],True,True),
    ('fe80::1',['fe80::/10'],True,True), ('2606:4700::1',['2606:4700::/32'],False,True),
    ('2606:4701::1',['2606:4700::/32'],False,False), ('0.0.0.0',['0.0.0.0/32'],True,False),
    ('224.0.0.1',['224.0.0.0/4'],True,False), ('::',['::/128'],True,False),
    ('ff02::1',['ff02::/16'],True,False)])
def test_address_family_and_explicit_non_global_scope(value,ranges,non_global,allowed):
    assert network(ranges,non_global).permits(address(value)) is allowed


def test_complete_dns_answer_validation():
    permitted = network(['127.0.0.1', '::1'])
    assert checked_answers(['::1','127.0.0.1','::1'],permitted) == (['127.0.0.1','::1'],True)
    assert checked_answers(['127.0.0.1','127.0.0.2'],permitted)[1] is False
    for values, code in [([], 'DNS_NO_RESULTS'), (['::ffff:127.0.0.1'],'DNS_RESULT_INVALID'),
                         (['fe80::1%3'],'DNS_RESULT_INVALID'), (['127.0.0.1']*257,'DNS_RESULT_INVALID')]:
        with pytest.raises(ScopeViolation) as exc:
            checked_answers(values,permitted)
        assert exc.value.code == code


def test_system_resolver_interface_collects_a_and_aaaa_without_external_dns():
    async def flow():
        loop = asyncio.get_running_loop()
        calls=[]
        async def fake(host,port,**kwargs):
            calls.append((host,port,kwargs))
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',port)),
                    (socket.AF_INET6,socket.SOCK_STREAM,6,'',('::1',port,0,0))]
        from unittest.mock import patch
        with patch.object(loop,'getaddrinfo',fake):
            assert await SystemResolver().resolve(HOST,443) == ['127.0.0.1','::1']
        assert calls == [(HOST,443,dict(family=socket.AF_UNSPEC,type=socket.SOCK_STREAM,proto=socket.IPPROTO_TCP,flags=0))]
        async def scoped(*args,**kwargs):
            return [(socket.AF_INET6,socket.SOCK_STREAM,6,'',('fe80::1',443,0,3))]
        with patch.object(loop,'getaddrinfo',scoped), pytest.raises(ValueError):
            await SystemResolver().resolve(HOST,443)
    asyncio.run(flow())


def test_peer_comparison_is_before_tls_and_rejects_port_family_and_scope():
    assert verify_peer(('127.0.0.1',443),'127.0.0.1',443)==('127.0.0.1',443)
    assert verify_peer(('::1',443,0,0),'::1',443)==('::1',443)
    for peer in [('127.0.0.2',443),('127.0.0.1',444),('::1',443,0,1),('::ffff:127.0.0.1',443,0,0),None]:
        with pytest.raises(ScopeViolation) as exc:
            verify_peer(peer,'127.0.0.1',443)
        assert exc.value.code=='DNS_PEER_MISMATCH'


def test_real_socket_does_not_resolve_again_after_check_and_keeps_sni_host():
    with certificates(dns_name=HOST) as material:
        trust=load_trust(material['ca_file'])
        api=AttachmentService('cookie',True)
        hosts,sni=[],[]
        material['server_context'].set_servername_callback(lambda _s,h,_c:sni.append(h))
        with attachment_server(api,ssl_context=material['server_context'],observed_hosts=hosts) as port:
            target=TargetPolicy('lab-web','https',HOST,port,network())
            resolver=TestResolver('rebind')  # A second resolve would return the unapproved address.
            observation={'origin':target.base_url}
            async def flow():
                transport=DomainTransport(target,trust,resolver,observation)
                async with httpx.AsyncClient(transport=transport,trust_env=False) as client:
                    # Even a caller-supplied SNI extension cannot override the registered identity.
                    return await client.get(target.base_url+'/gateway/session/profile',extensions={'sni_hostname':'other.securityai.test'})
            with forbid_hostname_lookup() as unexpected:
                response=asyncio.run(flow())
            assert response.status_code==401 and not unexpected and len(resolver.calls)==1
            assert observation['peer_verified'] and observation['selected_ip']==observation['peer_ip']=='127.0.0.1'
            assert sni==[HOST] and hosts==[f'{HOST}:{port}']


def test_real_tcp_peer_mismatch_seam_prevents_tls_and_http(monkeypatch):
    import worker.domain_transport as transport_module
    with certificates(dns_name=HOST) as material:
        api=AttachmentService('cookie',True)
        counts=dict(tcp_accepted=0,tls_handshake_attempts=0,tls_handshake_failed=0,tls_handshake_completed=0)
        def mismatch(peer,selected,port):
            assert peer[0]==selected=='127.0.0.1'
            raise ScopeViolation('DNS_PEER_MISMATCH','simulated peer mismatch')
        monkeypatch.setattr(transport_module,'verify_peer',mismatch)
        with attachment_server(api,ssl_context=material['server_context'],connection_counts=counts) as port:
            target=TargetPolicy('lab-web','https',HOST,port,network())
            observation={'origin':target.base_url}
            async def flow():
                async with httpx.AsyncClient(transport=DomainTransport(target,load_trust(material['ca_file']),TestResolver(),observation),trust_env=False) as client:
                    await client.get(target.base_url+'/gateway/session/profile')
            with pytest.raises(ScopeViolation) as exc:
                asyncio.run(flow())
            assert exc.value.code=='DNS_PEER_MISMATCH'
        assert api.received==0 and counts['tcp_accepted']==1 and counts['tls_handshake_completed']==0
        assert observation['stage']=='peer' and not observation.get('tls_attempts',0)


def test_resolver_timeout_does_not_connect():
    class SlowResolver:
        async def resolve(self,*args):
            await asyncio.sleep(10)
    with certificates(dns_name=HOST) as material:
        target=TargetPolicy('lab-web','https',HOST,443,network())
        observation={'origin':target.base_url}
        backend=PinnedBackend(target,load_trust(material['ca_file']),SlowResolver(),observation)
        with pytest.raises(ScopeViolation) as exc:
            asyncio.run(backend.connect_tcp(HOST,443,timeout=.01))
        assert exc.value.code=='DNS_LOOKUP_FAILED' and not observation.get('tcp_attempts')


def test_no_dns_ca_or_network_override_in_tool_contract():
    payload=dict(run_id='test',target_id='lab-web',account_ref='user-a',operation='login',resource_id=None,
                 expected_snapshot_sha256='0'*64)
    for key,value in [('url','https://other.test'),('dns_server','127.0.0.1'),('resolver','test'),
                      ('allowed_ip_ranges',['0.0.0.0/0']),('ca_bundle','x'),('verify',False)]:
        with pytest.raises(ValidationError):
            StepRequest.model_validate(dict(payload,**{key:value}))


def test_saved_ip_https_and_http_plans_and_replay_unchanged():
    for root in [Path('reports/local_https_verification_20261114'),Path('reports/independent_api_validation_20261113')]:
        for row in json.loads((root/'matrix.json').read_text())['cases']:
            folder=root/row['path']
            for path in folder.rglob('plan.json'):
                plan=parse_plan(path)
                assert 'domain' not in plan.policy.scope_policy.model_dump(mode='json')
                assert plan_hash(plan.model_dump(mode='json'))==plan.plan_sha256
            if row.get('run_id'):
                assert replay(folder/'runs'/row['run_id'])['verdict_matches']


def test_generic_registry_domain_snapshot_and_network_digest(tmp_path):
    config=json.loads(Path('config/targets.json').read_text())
    config['targets']['lab-web'].update(origin=f'https://{HOST}:443',network=network().model_dump(mode='json'))
    path=tmp_path/'scope.json'
    harness.write_json(path,config)
    with certificates(dns_name=HOST) as material:
        one=bind_registry_tls(load_scope_registry(path),material['ca_file'])
        scope=one.snapshot('lab-web','access-control-http',WorkerLimits())
        assert scope.record().domain.hostname==HOST
        assert scope.record().tls.verification=='dedicated-ca-dns-san-v1'
        config['targets']['lab-web']['network']['allowed_ip_ranges'].append('127.0.0.2')
        harness.write_json(path,config)
        two=bind_registry_tls(load_scope_registry(path),material['ca_file'])
        assert one.config_digest('lab-web')!=two.config_digest('lab-web')
        assert scope.snapshot_sha256!=two.snapshot('lab-web','access-control-http',WorkerLimits()).snapshot_sha256


def test_supported_public_transport_versions():
    assert httpx.__version__=='0.28.1' and httpcore.__version__=='1.0.9'
    assert issubclass(DomainTransport,httpx.AsyncBaseTransport)
    assert issubclass(PinnedBackend,httpcore.AsyncNetworkBackend)


@pytest.mark.parametrize('case,reason',[('untrusted_ca','TLS_CERT_UNTRUSTED'),('expired','TLS_CERT_EXPIRED')])
def test_domain_reuses_strict_ca_and_expiry_validation(case,reason):
    with certificates(case,dns_name=HOST) as material:
        api=AttachmentService('cookie',True)
        with attachment_server(api,ssl_context=material['server_context']) as port:
            target=TargetPolicy('lab-web','https',HOST,port,network())
            observation={'origin':target.base_url}
            async def flow():
                async with httpx.AsyncClient(transport=DomainTransport(target,load_trust(material['ca_file']),TestResolver(),observation),trust_env=False) as client:
                    await client.get(target.base_url+'/gateway/session/profile')
            with forbid_hostname_lookup(), pytest.raises(ScopeViolation) as exc:
                asyncio.run(flow())
            assert exc.value.code==reason and observation['reason_code']==reason and api.received==0


def test_ca_drift_between_tcp_and_tls_closes_socket(monkeypatch):
    with certificates(dns_name=HOST) as material:
        trust=load_trust(material['ca_file'])
        api=AttachmentService('cookie',True)
        counts=dict(tcp_accepted=0,tls_handshake_attempts=0,tls_handshake_failed=0,tls_handshake_completed=0)
        original=PinnedBackend.record_peer
        def change_after_connect(self,peer):
            original(self,peer)
            material['ca_file'].write_bytes(material['alternate_bundle'])
        monkeypatch.setattr(PinnedBackend,'record_peer',change_after_connect)
        with attachment_server(api,ssl_context=material['server_context'],connection_counts=counts) as port:
            target=TargetPolicy('lab-web','https',HOST,port,network())
            observation={'origin':target.base_url}
            async def flow():
                async with httpx.AsyncClient(transport=DomainTransport(target,trust,TestResolver(),observation),trust_env=False) as client:
                    await client.get(target.base_url+'/gateway/session/profile')
            with pytest.raises(ScopeViolation) as exc:
                asyncio.run(flow())
            assert exc.value.code=='TLS_TRUST_CHANGED_RESTART_REQUIRED'
        assert api.received==0 and counts['tls_handshake_failed']==1
        assert not observation.get('tls_attempts',0) and observation['peer_verified']


def test_no_address_retry_after_connect_error(monkeypatch):
    class Resolver:
        async def resolve(self,*args):
            return ['127.0.0.2','127.0.0.1']
    with certificates(dns_name=HOST) as material:
        target=TargetPolicy('lab-web','https',HOST,443,network(['127.0.0.1','127.0.0.2']))
        observation={'origin':target.base_url}
        calls=[]
        async def flow():
            loop=asyncio.get_running_loop()
            async def refused(sock,endpoint):
                calls.append(endpoint)
                raise OSError('synthetic refusal')
            from unittest.mock import patch
            with patch.object(loop,'sock_connect',refused):
                async with httpx.AsyncClient(transport=DomainTransport(target,load_trust(material['ca_file']),Resolver(),observation),trust_env=False) as client:
                    await client.get(target.base_url+'/gateway/session/profile')
        with pytest.raises(ScopeViolation) as exc:
            asyncio.run(flow())
        assert exc.value.code=='DOMAIN_CONNECTION_FAILED' and calls==[('127.0.0.1',443)]
