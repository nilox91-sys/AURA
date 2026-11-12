"""Provider metadata. Model catalogs are discovered; paid providers are never automatic fallbacks."""
PROVIDERS = {
 'openrouter':dict(label='OpenRouter',key='openrouter_api_key',base='https://openrouter.ai/api/v1',
    keys_url='https://openrouter.ai/settings/keys',default='openrouter/free',kind='cloud',note='Un account per più modelli. Le opzioni gratuite hanno quote; gli altri modelli possono essere a pagamento.'),
 'groq':dict(label='Groq',key='groq_api_key',base='https://api.groq.com/openai/v1',
    keys_url='https://console.groq.com/keys',default='openai/gpt-oss-20b',kind='cloud',note='Risposte rapide. Disponibilità e quota dipendono dal tuo account.'),
 'gemini':dict(label='Google Gemini',key='gemini_api_key',base='https://generativelanguage.googleapis.com/v1beta',
    keys_url='https://aistudio.google.com/apikey',default='gemini-2.5-flash',kind='cloud',note='Modelli Google. Usa la chiave di AI Studio; verifica quote e condizioni del tuo piano.'),
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
 'ollama':dict(label='Ollama · sul PC',key=None,host='ollama_host',default='',kind='local',
    keys_url='https://ollama.com/download',note='Avvia Ollama e installa un modello. Le conversazioni restano sull’indirizzo locale scelto.'),
 'lmstudio':dict(label='LM Studio · sul PC',key='lmstudio_api_key',host='lmstudio_host',default='',kind='local',
    keys_url='https://lmstudio.ai/docs/developer/core/server',note='Avvia il server in LM Studio. La chiave è facoltativa, se hai abilitato l’autenticazione del server.'),
 'compatible':dict(label='Altro servizio compatibile',key='compatible_api_key',host='compatible_base_url',default='',kind='custom',
    keys_url='https://platform.openai.com/docs/api-reference/chat',note='Endpoint compatibile con Chat Completions. Indica la base URL (ad esempio /v1), il modello e l’eventuale chiave.'),
}
EXTRA_PROVIDERS={'openai','anthropic','mistral','deepseek','lmstudio','compatible'}


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
