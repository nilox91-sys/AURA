"""Optional single-owner GitHub sign-in. Device codes stay server-side; tokens are discarded."""
from datetime import timedelta
import hashlib,json,os,re,secrets,tempfile,time
from pathlib import Path
from threading import Lock
import requests
from flask import Blueprint,jsonify,request,session,redirect,render_template


class GithubAccount:
    def __init__(self,app,settings,data_dir):
        self.settings=settings;self.folder=Path(data_dir)/'.aura-auth'
        self.folder.mkdir(parents=True,exist_ok=True)
        secret=self.folder/'session.key'
        try:
            with secret.open('xb') as stream:stream.write(secrets.token_bytes(32))
        except FileExistsError:pass
        app.secret_key=secret.read_bytes()
        app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
                          PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
        self.flows={};self.lock=Lock();self.owner_path=self.folder/'owner.json'
        blueprint=Blueprint('github_account',__name__)
        blueprint.add_url_rule('/login','login',lambda:render_template('login.html'))
        blueprint.add_url_rule('/api/github/status','status',self.status)
        blueprint.add_url_rule('/api/github/start','start',self.start,methods=['POST'])
        blueprint.add_url_rule('/api/github/poll','poll',self.poll,methods=['POST'])
        blueprint.add_url_rule('/api/github/logout','logout',self.logout,methods=['POST'])
        blueprint.add_url_rule('/api/github/disconnect','disconnect',self.disconnect,methods=['POST'])
        app.register_blueprint(blueprint)

        @app.before_request
        def require_account():
            if not settings.get('github_require_login',False) or self.authenticated():return
            if request.path=='/login' or request.path.startswith('/static/') or request.path in {
                    '/api/github/status','/api/github/start','/api/github/poll','/api/health'}:return
            if request.path=='/api/status':
                return jsonify(status='online',app_id='aura-local',app_version=app.config.get('AURA_VERSION','2.0.0'),
                    project_id=hashlib.sha256(app.root_path.casefold().encode()).hexdigest()[:16],authentication_required=True)
            if request.path.startswith('/api/'):
                return jsonify(status='error',error='Accedi con GitHub per continuare.',login_required=True),401
            return redirect('/login')

    def owner(self):
        try:return json.loads(self.owner_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):return {}

    def authenticated(self):
        owner=self.owner()
        return bool(owner.get('id') and session.get('github_id')==owner.get('id'))

    @staticmethod
    def github(method,url,**kwargs):
        with requests.Session() as connection:
            connection.trust_env=False
            headers={'Accept':'application/json','User-Agent':'AURA-local-companion'}
            headers.update(kwargs.pop('headers',{}))
            with connection.request(method,url,headers=headers,allow_redirects=False,timeout=(5,15),stream=True,**kwargs) as response:
                if not 200<=response.status_code<300:raise requests.HTTPError(response=response)
                blocks=[];size=0
                for block in response.iter_content(16384):
                    size+=len(block)
                    if size>128*1024:raise ValueError('GitHub response bounds')
                    blocks.append(block)
                result=json.loads(b''.join(blocks))
                if not isinstance(result,dict):raise ValueError('GitHub response format')
                return result

    def status(self):
        profile=self.owner() if self.authenticated() else None
        return jsonify(configured=bool(self.settings.get('github_client_id','')),
            authenticated=bool(profile),profile=profile,require_login=self.settings.get('github_require_login',False))

    def start(self):
        client=self.settings.get('github_client_id','')
        if not client:return jsonify(error='Inserisci il Client ID della tua applicazione GitHub nelle impostazioni.'),400
        try:
            result=self.github('POST','https://github.com/login/device/code',data={'client_id':client})
            code=result.get('device_code');user_code=result.get('user_code')
            if not isinstance(code,str) or not 1<=len(code)<=512 or not isinstance(user_code,str) or not re.fullmatch(r'[A-Za-z0-9-]{4,20}',user_code):
                return jsonify(error='GitHub non ha avviato l’accesso. Verifica Client ID e attivazione Device Flow.'),400
            expires=max(60,min(1800,int(result.get('expires_in',900))))
            interval=max(5,min(60,int(result.get('interval',5))))
            flow=secrets.token_urlsafe(32);now=time.monotonic()
            with self.lock:
                self.flows={k:v for k,v in self.flows.items() if v['expires']>now}
                if len(self.flows)>=32:return jsonify(error='Troppi accessi in corso. Attendi qualche minuto.'),429
                self.flows[flow]={'client':client,'code':code,'expires':now+expires,'next':now+interval,'interval':interval}
            session['github_flow']=flow
            return jsonify(user_code=user_code,verification_uri='https://github.com/login/device',expires_in=expires,interval=interval)
        except (requests.RequestException,ValueError,TypeError):
            return jsonify(error='GitHub non è raggiungibile o non ha accettato il Client ID.'),503

    def poll(self):
        flow_id=session.get('github_flow');now=time.monotonic()
        with self.lock:
            flow=self.flows.get(flow_id)
            if not flow or flow['expires']<=now or flow['client']!=self.settings.get('github_client_id',''):
                self.flows.pop(flow_id,None)
                return jsonify(state='expired',error='Codice scaduto. Avvia nuovamente l’accesso.'),410
            if now<flow['next']:
                return jsonify(state='pending',interval=max(1,int(flow['next']-now)+1))
            flow['next']=now+flow['interval']
            values=dict(flow)
        try:
            result=self.github('POST','https://github.com/login/oauth/access_token',data={
                'client_id':values['client'],'device_code':values['code'],'grant_type':'urn:ietf:params:oauth:grant-type:device_code'})
            error=result.get('error')
            if error=='authorization_pending':return jsonify(state='pending',interval=values['interval'])
            if error=='slow_down':
                with self.lock:
                    if flow_id in self.flows:
                        self.flows[flow_id]['interval']=min(60,values['interval']+5)
                        self.flows[flow_id]['next']=time.monotonic()+self.flows[flow_id]['interval']
                return jsonify(state='pending',interval=min(60,values['interval']+5))
            token=result.get('access_token')
            if error or not isinstance(token,str) or not 1<len(token)<4096:
                with self.lock:self.flows.pop(flow_id,None)
                return jsonify(state='denied',error='Accesso non autorizzato o scaduto. Puoi riprovare.'),403
            user=self.github('GET','https://api.github.com/user',headers={'Authorization':'Bearer '+token,'X-GitHub-Api-Version':'2022-11-28'})
            # The bearer token is never persisted, sent to the browser or used as an AI key.
            del token
            identity=user.get('id');login=user.get('login')
            if type(identity) is not int or identity<=0 or not isinstance(login,str) or not re.fullmatch(r'[A-Za-z0-9-]{1,39}',login):
                raise ValueError('GitHub identity')
            owner=self.owner()
            if self.settings.get('github_require_login',False) and owner.get('id') not in (None,identity):
                with self.lock:self.flows.pop(flow_id,None)
                return jsonify(state='denied',error='Usa l’account GitHub già collegato a questa installazione.'),403
            profile={'id':identity,'login':login,'name':str(user.get('name') or login)[:100],
                     'avatar_url':f'https://avatars.githubusercontent.com/u/{identity}?v=4','html_url':'https://github.com/'+login}
            with self.lock:
                with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=self.folder,delete=False) as stream:
                    json.dump(profile,stream,ensure_ascii=False);temporary=stream.name
                os.replace(temporary,self.owner_path)
                self.flows.pop(flow_id,None)
            session.clear();session['github_id']=identity;session.permanent=True
            return jsonify(state='authenticated',profile=profile)
        except (requests.RequestException,ValueError,TypeError):
            return jsonify(state='pending',interval=values['interval'],error='Verifica GitHub temporaneamente non disponibile.'),503

    def logout(self):
        with self.lock:self.flows.pop(session.get('github_flow'),None)
        session.clear()
        return jsonify(status='success',redirect='/login' if self.settings.get('github_require_login',False) else '/settings#github')

    def disconnect(self):
        if self.settings.get('github_require_login',False):
            return jsonify(error='Disattiva prima l’accesso obbligatorio e salva le impostazioni.'),400
        self.owner_path.unlink(missing_ok=True)
        session.clear()
        return jsonify(status='success')
