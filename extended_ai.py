"""Native OpenAI/Claude and compatible endpoints, with bounded responses and safe errors."""
import json,re
import requests
from provider_registry import PROVIDERS,base_url
from runtime_utils import provider_timeout
from provider_errors import ProviderHTTPError


def request_json(method,url,headers=None,payload=None,timeout=None):
    with requests.Session() as session:
        session.trust_env=False
        with session.request(method,url,headers=headers,json=payload,timeout=timeout or provider_timeout(),
                             allow_redirects=False,stream=True) as response:
            if 300<=response.status_code<400:raise requests.HTTPError(response=response)
            chunks=[];size=0
            for block in response.iter_content(65536):
                size+=len(block)
                if size>4*1024*1024:raise ValueError('Risposta del servizio troppo grande')
                chunks.append(block)
            content=b''.join(chunks)
            if response.status_code>=400:
                try:payload=json.loads(content)
                except ValueError:payload={}
                raise ProviderHTTPError(response,payload)
            return json.loads(content)


def call_extra(provider,model,messages,settings,options,schema):
    info=PROVIDERS[provider]
    import os
    key=settings.get(info['key']) or os.getenv(info['key'].upper(),'') if info.get('key') else ''
    headers={'Content-Type':'application/json'}
    temperature={'precise':.2,'balanced':.45,'creative':.8}.get(settings.get('creativity'),.45)
    if provider=='anthropic':
        headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
        system='\n'.join(m['content'] for m in messages if m['role']=='system')
        turns=[m for m in messages if m['role']!='system']
        data=request_json('POST',base_url(provider,settings)+'/messages',headers,
            {'model':model,'system':system,'messages':turns,'max_tokens':options['max_tokens'],'temperature':temperature})
        return ''.join(block.get('text','') for block in data.get('content',[]) if block.get('type')=='text'),data.get('stop_reason')=='max_tokens',data
    if key:headers['Authorization']='Bearer '+key
    if provider=='openai':
        payload={'model':model,'input':messages,'max_output_tokens':options['max_tokens'],'store':False,
                 'text':{'format':{'type':'json_schema','name':'aura_reply','schema':schema,'strict':True}}}
        if model.startswith(('gpt-4','chatgpt-4')):payload['temperature']=temperature
        data=request_json('POST',base_url(provider,settings)+'/responses',headers,payload)
        text=''.join(c.get('text','') or c.get('refusal','') for item in data.get('output',[]) if item.get('type')=='message'
                     for c in item.get('content',[]) if c.get('type') in ('output_text','refusal'))
        return text,data.get('status')=='incomplete',data
    payload={'model':model,'messages':messages,'max_tokens':options['max_tokens'],'temperature':temperature,'stream':False}
    data=request_json('POST',base_url(provider,settings)+'/chat/completions',headers,payload)
    choice=data['choices'][0]
    return choice.get('message',{}).get('content',''),choice.get('finish_reason')=='length',data


def discover(provider,settings):
    import os
    info=PROVIDERS[provider];key=settings.get(info.get('key','')) or os.getenv(str(info.get('key','')).upper(),'')
    if info.get('key') and not key and provider not in {'lmstudio','compatible'}:
        return {'id':provider,'state':'not_configured','message':'Inserisci la chiave del servizio.','models':[]}
    headers={'Authorization':'Bearer '+key} if key else {}
    if provider=='anthropic':headers={'x-api-key':key,'anthropic-version':'2023-06-01'}
    if provider=='gemini':headers={'x-goog-api-key':key}
    base=base_url(provider,settings)
    path='/api/tags' if provider=='ollama' else '/models?pageSize=1000' if provider=='gemini' else '/models'
    if provider=='openrouter':
        request_json('GET',base+'/key',headers,timeout=(3,10))
    if provider=='huggingface':
        request_json('GET','https://huggingface.co/api/whoami-v2',headers,timeout=(3,10))
    data=request_json('GET',base+path,headers,timeout=(3,10))
    entries=data.get('models',[]) if provider in {'gemini','ollama'} else data.get('data',[])
    models=[]
    for item in entries[:4000]:
        if not isinstance(item,dict):continue
        name=item.get('name','') if provider in {'gemini','ollama'} else item.get('id','')
        if not isinstance(name,str):continue
        name=name.removeprefix('models/')
        if provider=='gemini' and 'generateContent' not in item.get('supportedGenerationMethods',[]):continue
        if not isinstance(name,str) or not re.fullmatch(r'[\w./:@+-]{1,160}',name):continue
        if any(word in name.lower() for word in ('embedding','whisper','tts','realtime','transcrib','dall-e','moderation','lyria','robotics','antigravity','deep-research','computer-use','nano-banana','customtools')):continue
        if provider=='gemini' and 'image' in name.lower():continue
        modalities=item.get('architecture',{}).get('output_modalities',[])
        if modalities and 'text' not in modalities:continue
        if item.get('capabilities',{}).get('completion_chat') is False:continue
        models.append(name)
    preferred=info.get('default')
    models=sorted(set(models),key=lambda name:(name!=preferred,provider=='gemini' and name.startswith('gemini-2.5-'),name))[:2000]
    return {'id':provider,'state':'available' if models else 'no_models','models':models,
            'message':f'Catalogo raggiunto · {len(models)} modelli. La quota e la capacità di rispondere si verificano con “Prova una risposta”.' if models else 'Servizio raggiunto; nessun modello disponibile. Puoi indicare un identificativo manualmente.'}
