"""Settings operations with no conversation content or credentials in responses."""
import json,os,re,time
from pathlib import Path
from flask import Blueprint,jsonify,request,Response
from ai_engine import LLMEngine, generation_options, generation_info, REPLY_SCHEMA
from extended_ai import discover
from provider_registry import PROVIDERS
from runtime_utils import cache_lock,provider_deadline
from settings_store import SECRET_KEYS


def register_settings_api(app,manager,defaults,cache_dir):
    api=Blueprint('settings_operations',__name__)

    @api.post('/api/integrations/check')
    def check():
        body=request.get_json(silent=True)
        provider=body.get('provider') if isinstance(body,dict) else None
        if provider not in PROVIDERS:return jsonify(error='Servizio non riconosciuto.'),400
        settings=manager.get_all();keys=LLMEngine.provider_keys(settings)
        try:
            result=discover(provider,settings)
            if result['state']=='available':
                LLMEngine.health.success(provider,keys,models=result['models'],verified=True)
            return jsonify(result)
        except Exception as error:
            message,code=LLMEngine.health.failure(provider,keys,'*',error)
            return jsonify(id=provider,state='unavailable',message=message,http_status=code,models=[]),502

    @api.post('/api/integrations/test')
    def test():
        body=request.get_json(silent=True)
        if not isinstance(body,dict):return jsonify(error='Dati non validi.'),400
        provider=body.get('provider');model=body.get('model')
        if provider not in PROVIDERS or not isinstance(model,str) or not re.fullmatch(r'[\w./:@+-]{1,160}',model):
            return jsonify(error='Seleziona un servizio e un modello validi.'),400
        settings=manager.get_all();keys=LLMEngine.provider_keys(settings)
        if not keys.get(provider):return jsonify(error='Configura prima il servizio.'),400
        options=generation_options.set({'max_tokens':512,'reasoning_effort':'low'})
        deadline=provider_deadline.set(time.monotonic()+30);trace=generation_info.set({})
        started=time.perf_counter()
        try:
            raw=LLMEngine.call_provider(provider,model,[{'role':'system','content':'Rispondi in italiano con JSON: {"emozione":"normale","testo":"Connessione riuscita."}.'},
                {'role':'user','content':'Scrivi soltanto: Connessione riuscita.'}],settings)
            text,_=LLMEngine.parse_json_response(raw)
            if not text:raise ValueError('Risposta vuota')
            LLMEngine.health.success(provider,keys,model=model)
            return jsonify(status='success',message=text[:500],latency_ms=round((time.perf_counter()-started)*1000))
        except Exception as error:
            message,code=LLMEngine.health.failure(provider,keys,model,error)
            return jsonify(status='error',error=message,http_status=code),502
        finally:
            generation_options.reset(options);provider_deadline.reset(deadline);generation_info.reset(trace)

    @api.post('/api/integrations/remove-key')
    def remove_key():
        body=request.get_json(silent=True);provider=body.get('provider') if isinstance(body,dict) else None
        if provider not in PROVIDERS or not PROVIDERS[provider].get('key'):
            return jsonify(error='Servizio non valido.'),400
        key=PROVIDERS[provider]['key'];manager.update({},clear_keys={key})
        return jsonify(status='success',environment_key_present=bool(os.getenv(key.upper())))

    @api.get('/api/preferences/export')
    def export():
        settings=manager.get_all()
        excluded=SECRET_KEYS|{'github_client_id','github_require_login','schema_version'}
        payload={'format':'aura-preferences','version':1,'preferences':{k:v for k,v in settings.items() if k not in excluded}}
        return Response(json.dumps(payload,ensure_ascii=False,indent=2),mimetype='application/json',
                        headers={'Content-Disposition':'attachment; filename="aura-preferenze.json"'})

    def audio_files():
        return [p for p in Path(cache_dir).iterdir() if p.is_file() and not p.is_symlink()
                and re.fullmatch(r'[0-9a-f]{64}\.(mp3|wav)',p.name)]

    @api.route('/api/audio-cache',methods=['GET','POST'])
    def cache():
        with cache_lock:
            files=audio_files()
            if request.method=='POST':
                for item in files:item.unlink(missing_ok=True)
                files=[]
            return jsonify(files=len(files),bytes=sum(p.stat().st_size for p in files))

    app.register_blueprint(api)
