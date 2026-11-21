"""Independent in-memory JSON test API. No TargetStore, lab headers, canaries or DBs."""
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import socket
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import uvicorn

ROOT=Path(__file__).resolve().parents[1]


def settings(auth='cookie',origin='http://127.0.0.1:18080'):
    value=json.loads((ROOT/'config/targets.operator.json').read_text())
    entry=value['targets']['lab-web']
    entry['origin']=origin
    entry['profile']['limits']['requests_per_second']=1000.0
    if auth=='bearer':
        entry['adapter'].update(auth_mode='bearer',cookie_name=None,token_field='access.token')
    return value


def schema_object(fields):
    return {'type':'object','properties':fields,'required':list(fields)}


def specification(auth='cookie'):
    string={'type':'string'}
    def response(schema): return {'description':'test response','content':{'application/json':{'schema':schema}}}
    security={'auth':{'type':'apiKey','in':'cookie','name':'session_key'} if auth=='cookie' else {'type':'http','scheme':'bearer'}}
    doc={'openapi':'3.0.3','info':{'title':'Independent ticket API','version':'1'},
      'components':{'securitySchemes':security},'security':[{'auth':[]}],
      'paths':{
        '/session':{'post':{'security':[],'requestBody':{'required':True,'content':{'application/json':{'schema':schema_object({'username':string,'password':string})}}},
           'responses':{'200':response(schema_object({'ok':{'type':'boolean'}}) if auth=='cookie' else schema_object({'access':schema_object({'token':string})}))}}},
        '/me':{'get':{'responses':{'200':response(schema_object({'user':schema_object({'id':string})}))}}},
        '/tickets/{resource_id}':{'get':{'parameters':[{'in':'path','name':'resource_id','required':True,'schema':{'type':'string','pattern':'^[A-Za-z0-9_-]{1,128}$','minLength':1,'maxLength':128}}],
            'responses':{'200':response(schema_object({'id':string,'owner':string,'private':{'type':'boolean'},'memo':string})),
                         '404':response(schema_object({'error':schema_object({'code':string})}))}}}}}
    if auth=='cookie':
        doc['paths']['/session']['post']['responses']['200']['headers']={'Set-Cookie':{'schema':{'type':'string'}}}
    return doc


class IndependentAPI:
    def __init__(self,auth='cookie',vulnerable=True,fault=None):
        self.auth,self.vulnerable,self.fault=auth,vulnerable,fault
        self.principals={'alice_17':'alice-17','bob_2048':'2048'}
        self.resources={'alice-17':'95a8a830-f123-4f62-b38b-004d428ecab1','2048':'ticket_2048'}
        self.passwords={u:secrets.token_urlsafe(24) for u in self.principals}
        self.proofs={p:secrets.token_urlsafe(32) for p in self.resources}
        self.sessions={}
        self.requests=[]
        self.identity_reads={}
        self.resource_reads={}
        self.shared_token=secrets.token_urlsafe(32)
        self.app=FastAPI(docs_url=None,redoc_url=None)
        @self.app.middleware('http')
        async def count(request,call_next):
            self.requests.append((request.method,request.url.path))
            return await call_next(request)
        @self.app.post('/session')
        async def login(request:Request):
            data=await request.json()
            user=data.get('username')
            if self.fault=='login_failed' or user not in self.passwords or self.passwords[user]!=data.get('password'):
                return JSONResponse({'error':'login failed'},401)
            token=self.shared_token if self.fault=='same_session' else secrets.token_urlsafe(32)
            self.sessions[token]=self.principals[user]
            response=JSONResponse({'access':{'token':token}} if auth=='bearer' else {'ok':True})
            if auth=='cookie': response.set_cookie('session_key',token,httponly=True,samesite='strict')
            return response
        def principal(request):
            token=request.headers.get('authorization','').removeprefix('Bearer ') if auth=='bearer' else request.cookies.get('session_key')
            return self.sessions.get(token)
        @self.app.get('/me')
        async def me(request:Request):
            who=principal(request)
            if not who: return JSONResponse({'error':'unauthorized'},401)
            self.identity_reads[who]=self.identity_reads.get(who,0)+1
            if self.fault=='session_expiry' and self.identity_reads[who]>1:
                return JSONResponse({'error':'expired'},401)
            if self.fault=='same_principal': who='alice-17'
            if self.fault=='identity_mismatch': who='unexpected-principal'
            return {'user':{'id':who}}
        @self.app.get('/tickets/{resource_id}')
        async def get_resource(resource_id:str,request:Request):
            who=principal(request)
            if not who: return JSONResponse({'error':'unauthorized'},401)
            owner=next((p for p,r in self.resources.items() if r==resource_id),None)
            if not owner: return JSONResponse({'error':{'code':'denied'}},404)
            self.resource_reads[resource_id]=self.resource_reads.get(resource_id,0)+1
            cross=owner!=who
            if self.fault=='common_error': return JSONResponse({'error':'missing'},404)
            if cross:
                if self.fault=='html': return Response('<html>login or WAF</html>',media_type='text/html')
                if self.fault=='redirect': return Response(status_code=302,headers={'Location':'/me'})
                if self.fault=='rate_limit': return JSONResponse({'error':self.proofs[owner]},429)
                if self.fault=='server_error': return JSONResponse({'error':self.passwords['bob_2048']},500)
                if self.fault=='duplicate_keys': return Response('{"id":"a","id":"b"}',media_type='application/json')
                if self.fault=='oversize': return JSONResponse({'memo':'x'*131072})
                if self.fault=='slow': await asyncio.sleep(1)
                if not self.vulnerable: return JSONResponse({'error':{'code':'denied'}},404)
            result={'id':resource_id,'owner':owner,'private':True,'memo':self.proofs[owner]}
            if self.fault=='public': result['private']=False
            if self.fault=='same_proof': result['memo']=self.proofs['alice-17']
            if self.fault=='missing_proof': result.pop('memo')
            if self.fault=='proof_changed' and self.resource_reads[resource_id]>=3: result['memo']=secrets.token_urlsafe(32)
            if self.fault=='wrong_id': result['id']='unregistered_resource'
            if self.fault=='wrong_owner': result['owner']='unregistered_principal'
            if self.fault=='wrong_type': result['id']=2048
            if self.fault=='a_contains_b' and owner=='alice-17': result['memo']=self.proofs['2048']
            return result

    def environment(self):
        return {'LAB_USER_A_PASSWORD':self.passwords['alice_17'],'LAB_USER_B_PASSWORD':self.passwords['bob_2048'],
                'OPERATOR_PROOF_A':self.proofs['alice-17'],'OPERATOR_PROOF_B':self.proofs['2048']}


@contextmanager
def local_server(app):
    """Test-only reserved loopback socket; stop only this newly-created server."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        sock.listen(128)
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,lifespan='on'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
        thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.02)
            if not server.started: raise RuntimeError('temporary test server failed to start')
            yield sock.getsockname()[1]
        finally:
            server.should_exit=True
            thread.join(timeout=10)
            if thread.is_alive(): raise RuntimeError('temporary test server failed to stop')
