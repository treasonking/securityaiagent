"""Local UI/API integration environment; reuses the independent attachment API."""
from contextlib import contextmanager
from pathlib import Path
import secrets
import socket

from controller.api import AppSettings,create_app
from controller.operator_client import ResourceClient,ResourcePolicyClient
from controller.workspace import Workspace,Profile
from scripts.run_domain_https_verification import domain_config
from scripts.run_independent_api_validation import write_json
from scripts.run_local_https_verification import new_worker
from validation.domain_https import HOST,TestResolver,forbid_hostname_lookup
from validation.independent_api.api import AttachmentService,attachment_server
from validation.independent_api.configuration import specification
from validation.independent_api.transport import worker_server
from validation.local_https import certificates


@contextmanager
def workspace_lab(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    api=AttachmentService('cookie',True)
    token,access,secret=(secrets.token_urlsafe(36) for _ in range(3))
    env=dict(LAB_USER_A_PASSWORD=api.members[0].password,LAB_USER_B_PASSWORD=api.members[1].password,
             OPERATOR_PROOF_A=api.attachments[0].receipt,OPERATOR_PROOF_B=api.attachments[1].receipt)
    counts=dict(tcp_accepted=0,tls_handshake_attempts=0,tls_handshake_failed=0,tls_handshake_completed=0)
    with certificates(dns_name=HOST) as material,forbid_hostname_lookup():
        with attachment_server(api,ssl_context=material['server_context'],connection_counts=counts) as port:
            config=domain_config('cookie',port)
            registry,worker_registry,source=root/'registered.json',root/'worker.json',root/'openapi.json'
            write_json(registry,config);write_json(worker_registry,config);write_json(source,specification('cookie'))
            service,app=new_worker(worker_registry,env,token,material['ca_file'])
            service._domain_resolver=TestResolver()
            context=worker_server(app)
            worker_port=context.__enter__()
            base=f'http://127.0.0.1:{worker_port}'
            workspace=Workspace(profiles={'attachments':Profile(profile_id='attachments',name='프로젝트 첨부파일 · 등록 프로필',source_path=str(source),registry_path=str(registry))},
                state_path=root/'workspace',reports_path=root/'runs',policy_client=ResourcePolicyClient(base,token),
                client_factory=lambda t:ResourceClient(base,token,t),timeout=60)
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));controller_port=reservation.getsockname()[1]
            origin=f'http://127.0.0.1:{controller_port}'
            settings=AppSettings(database_path=root/'controller-test.sqlite3',reports_path=root/'runs',
                access_token=access,session_secret=secret,allowed_origins=frozenset({origin}),
                allowed_hosts=frozenset({'127.0.0.1'}),allowed_clients=frozenset({'127.0.0.1'}))
            controller=create_app(settings=settings,clients={},workspace=workspace)
            def change_policy():
                nonlocal context,service,app
                context.__exit__(None,None,None)
                config['targets']['lab-web']['profile']['revision']+=1
                write_json(worker_registry,config)
                service,app=new_worker(worker_registry,env,token,material['ca_file'])
                service._domain_resolver=TestResolver()
                context=worker_server(app,worker_port)
                context.__enter__()
            try:
                with worker_server(controller,controller_port):
                    yield dict(origin=origin,access_token=access,api=api,counts=counts,workspace=workspace,
                        change_policy=change_policy,sync_profile=lambda:write_json(registry,config),
                        private_values=[token,access,secret,*material['private_values'],str(material['private_directory']),material['private_directory'].as_posix()],
                        certificate=material['public'])
            finally:
                context.__exit__(None,None,None)
