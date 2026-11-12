"""Provider metadata. Model catalogs are discovered; paid providers are never automatic fallbacks."""
PROVIDERS = {
 'openrouter':dict(label='OpenRouter',key='openrouter_api_key',base='https://openrouter.ai/api/v1',
    keys_url='https://openrouter.ai/settings/keys',default='openrouter/free',kind='cloud',note='Un account per più modelli. Le opzioni gratuite hanno quote; gli altri modelli possono essere a pagamento.'),
 'groq':dict(label='Groq',key='groq_api_key',base='https://api.groq.com/openai/v1',
    keys_url='https://console.groq.com/keys',default='openai/gpt-oss-20b',kind='cloud',note='Risposte rapide. Disponibilità e quota dipendono dal tuo account.'),
 'gemini':dict(label='Google Gemini',key='gemini_api_key',base='https://generativelanguage.googleapis.com/v1beta',
    keys_url='https://aistudio.google.com/apikey',default='gemini-3.1-flash-lite',kind='cloud',note='Modelli Google. Usa la chiave di AI Studio; verifica quote e condizioni del tuo piano. I modelli 2.5 possono comparire nel catalogo ma essere dismessi per i nuovi account.'),
 'huggingface':dict(label='Hugging Face',key='hf_api_key',base='https://router.huggingface.co/v1',
    keys_url='https://huggingface.co/settings/tokens',default='openai/gpt-oss-120b',kind='cloud',note='Inference Providers. Lo stesso campo token è usato dalla voce Irodori; la verifica AI è separata dalla quota vocale.'),
 'openai':dict(label='OpenAI',key='openai_api_key',base='https://api.openai.com/v1',
    keys_url='https://platform.openai.com/api-keys',default='gpt-4.1-mini',kind='cloud',note='API a consumo, separate dall’abbonamento ChatGPT. Scegli un modello disponibile sul tuo account.'),
 'anthropic':dict(label='Anthropic · Claude',key='anthropic_api_key',base='https://api.anthropic.com/v1',
    keys_url='https://platform.claude.com/settings/keys',default='',kind='cloud',note='API Claude a consumo. La verifica mostra i modelli accessibili al tuo account.'),
 'mistral':dict(label='Mistral',key='mistral_api_key',base='https://api.mistral.ai/v1',
    keys_url='https://console.mistral.ai/api-keys',default='mistral-small-latest',kind='cloud',note='Modelli Mistral. Crediti e disponibilità dipendono dal tuo piano.'),
 'deepseek':dict(label='DeepSeek',key='deepseek_api_key',base='https://api.deepseek.com',
    keys_url='https://platform.deepseek.com/api_keys',default='deepseek-flash',kind='cloud',note='API DeepSeek a consumo; il sito di chat e la chiave API sono servizi separati.'),
 'cerebras':dict(label='Cerebras',key='cerebras_api_key',base='https://api.cerebras.ai/v1',
    keys_url='https://cloud.cerebras.ai',default='',kind='cloud',note='API a consumo con eventuali crediti iniziali di prova. Leggi il catalogo del tuo account e scegli il modello; condizioni e disponibilità dipendono dal piano.'),
 'xai':dict(label='xAI · Grok',key='xai_api_key',base='https://api.x.ai/v1',
    keys_url='https://console.x.ai',default='',kind='cloud',note='API Grok a consumo, separate dall’abbonamento alla chat. Scegli un modello del catalogo del tuo account. AURA usa Responses senza archiviazione della conversazione richiesta all’API.'),
 'ollama':dict(label='Ollama · sul PC',key=None,host='ollama_host',default='',kind='local',
    keys_url='https://ollama.com/download',note='Avvia Ollama e installa un modello. Le conversazioni restano sull’indirizzo locale scelto.'),
 'lmstudio':dict(label='LM Studio · sul PC',key='lmstudio_api_key',host='lmstudio_host',default='',kind='local',
    keys_url='https://lmstudio.ai/docs/developer/core/server',note='Avvia il server in LM Studio. La chiave è facoltativa, se hai abilitato l’autenticazione del server.'),
 'compatible':dict(label='Altro servizio compatibile',key='compatible_api_key',host='compatible_base_url',default='',kind='custom',
    keys_url='https://platform.openai.com/docs/api-reference/chat',note='Endpoint compatibile con Chat Completions. Indica la base URL (ad esempio /v1), il modello e l’eventuale chiave.'),
}
EXTRA_PROVIDERS={'openai','anthropic','mistral','deepseek','cerebras','xai','lmstudio','compatible'}

# A free tier is an account offer, not a guarantee that every model is free.
SERVICE_PLANS={
 'openrouter':(['free','paid'],'Modelli gratuiti con quota e modelli a consumo','https://openrouter.ai/collections/free-models'),
 'groq':(['free','paid'],'Quota gratuita e piani a consumo','https://console.groq.com/docs/rate-limits'),
 'gemini':(['free','paid'],'Quota gratuita sui modelli idonei; piano a consumo','https://aistudio.google.com/docs/pricing'),
 'huggingface':(['trial','paid'],'Crediti di prova limitati, poi consumo','https://huggingface.co/docs/inference-providers/pricing'),
 'openai':(['paid'],'API a consumo · fatturazione separata da ChatGPT','https://developers.openai.com/api/docs/pricing'),
 'anthropic':(['paid'],'API a consumo · credito del tuo account','https://platform.claude.com/docs/en/about-claude/pricing'),
 'mistral':(['free','paid'],'Piano gratuito di valutazione e API a consumo','https://mistral.ai/pricing/'),
 'deepseek':(['paid'],'API a consumo · saldo necessario','https://api-docs.deepseek.com/quick_start/pricing'),
 'cerebras':(['trial','paid'],'Eventuali crediti iniziali e API a consumo','https://www.cerebras.ai/pricing'),
 'xai':(['paid'],'API a consumo · credito del tuo account','https://docs.x.ai/developers/models'),
 'ollama':(['local'],'Sul tuo PC · hardware e modello necessari','https://ollama.com/download'),
 'lmstudio':(['local'],'Sul tuo PC · hardware e modello necessari','https://lmstudio.ai/docs/developer/core/server'),
 'compatible':(['custom'],'Costo e condizioni del servizio configurato','https://platform.openai.com/docs/api-reference/chat'),
}
for name,(tiers,label,url) in SERVICE_PLANS.items():
    PROVIDERS[name].update(tiers=tiers,plan_label=label,pricing_url=url)


def visible_providers(settings):
    allowed=settings.get('ai_model_allowlist',[])
    if not allowed:return dict(PROVIDERS)
    ids={value.partition(':')[0] for value in allowed}
    return {name:info for name,info in PROVIDERS.items() if name in ids}


def visible_models(provider,settings,models=()):
    allowed=settings.get('ai_model_allowlist',[])
    if not allowed:return list(models)
    prefix=provider+':'
    return [value[len(prefix):] for value in allowed if value.startswith(prefix)]


def model_allowed(provider,model,settings):
    allowed=settings.get('ai_model_allowlist',[])
    return not allowed or provider+':'+model in allowed


def provider_key(provider, settings):
    import os
    info=PROVIDERS[provider]
    if not info.get('key'):return settings.get(info.get('host','')) or os.getenv('OLLAMA_HOST','http://localhost:11434')
    key=settings.get(info['key']) or os.getenv(info['key'].upper(),'')
    if provider in {'lmstudio','compatible'}:
        return (settings.get(info['host'],'').rstrip('/')+'\0'+key)
    return key


def base_url(provider,settings):
    info=PROVIDERS[provider]
    return (settings.get(info.get('host','')) or info.get('base','')).rstrip('/')
