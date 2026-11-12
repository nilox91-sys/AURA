"""Shared, non-secret defaults and validation for the personal settings UI."""
import ipaddress
from urllib.parse import urlsplit

EXTRA_DEFAULTS = {
    'ai_model_allowlist':[],
    'openai_api_key':'', 'anthropic_api_key':'', 'mistral_api_key':'', 'deepseek_api_key':'',
    'lmstudio_api_key':'', 'compatible_api_key':'',
    'lmstudio_host':'http://127.0.0.1:1234/v1', 'compatible_base_url':'http://127.0.0.1:1234/v1',
    'github_client_id':'', 'github_require_login':False,
    'assistant_tagline':'Curiosità in buona compagnia.', 'assistant_purpose':'Aiutami a capire, creare e dare forma alle idee.',
    'assistant_pronouns':'feminine', 'communication_tone':'warm', 'humor_level':'gentle',
    'emoji_style':'none', 'interests':'Tecnologia, anime, giochi e scienza',
    'custom_instructions':'', 'user_bio':'', 'welcome_message':'',
    'theme':'lavender', 'avatar_quality':'balanced', 'avatar_follow_cursor':True,
    'avatar_lipsync':True, 'avatar_motion':True, 'avatar_framing':'portrait',
    'voice_auto_listen':True, 'voice_greeting':False,
    'history_enabled':True, 'tts_cache_enabled':True, 'tts_cache_mb':128,
    'ai_timeout_seconds':65, 'creativity':'balanced',
}
ENUMS = {
    'assistant_pronouns':{'feminine','masculine','neutral'},
    'communication_tone':{'warm','neutral','energetic','formal'},
    'humor_level':{'none','gentle','playful'}, 'emoji_style':{'none','occasional','frequent'},
    'theme':{'lavender','midnight','forest'}, 'avatar_quality':{'balanced','light','fluid'},
    'avatar_framing':{'portrait','full'}, 'creativity':{'precise','balanced','creative'},
}
TEXT_LIMITS={'assistant_tagline':100,'assistant_purpose':240,'interests':240,
             'custom_instructions':3000,'user_bio':1200,'welcome_message':240,'github_client_id':100}
MULTILINE={'custom_instructions','user_bio','assistant_purpose'}


def local_endpoint(url):
    host=(urlsplit(url).hostname or '').lower()
    if host=='localhost':return True
    try:
        ip=ipaddress.ip_address(host)
        return (ip.is_loopback or ip.is_private) and not (ip.is_link_local or ip.is_multicast or ip.is_unspecified)
    except ValueError:
        return host.endswith('.local')


def validate_endpoint(value):
    url=urlsplit(value)
    try:url.port
    except ValueError:raise ValueError('Porta del servizio non valida.') from None
    if (url.scheme not in {'http','https'} or not url.hostname or url.username or url.password
            or url.query or url.fragment or (url.scheme=='http' and not local_endpoint(value))):
        raise ValueError('Usa HTTPS, oppure HTTP per un servizio locale; senza credenziali o parametri nell’indirizzo.')
    return value.rstrip('/')
