"""Classify upstream failures without returning provider messages or credentials to the UI."""
from datetime import datetime, timezone
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import requests


class ProviderHTTPError(requests.HTTPError):
    def __init__(self, response, payload):
        super().__init__('Provider HTTP error', response=response)
        self.payload = payload


def describe_error(provider, error):
    response = getattr(error, 'response', None)
    code = getattr(response, 'status_code', None)
    payload = getattr(error, 'payload', None)
    if payload is None and response is not None:
        try:
            payload = response.json()
        except (ValueError, requests.RequestException):
            payload = {}
    detail = payload.get('error', {}) if isinstance(payload, dict) else {}
    message = detail.get('message', '') if isinstance(detail, dict) else detail if isinstance(detail, str) else ''
    if not isinstance(message,str):message=''
    text = message.lower() if isinstance(message, str) else ''
    info = {'http_status': code, 'kind': 'unavailable', 'seconds': 15, 'provider_wide': False,
            'message': 'Servizio temporaneamente non raggiungibile.', 'action': 'Riprova tra poco.'}
    if code == 402:
        info.update(kind='balance', seconds=900, provider_wide=True, message='Credito API esaurito o non attivato.',
                    action='Controlla il saldo sul sito del servizio, oppure scegli un altro servizio. Una nuova chiave dello stesso account non aggiunge credito.')
    elif code == 401:
        info.update(kind='authentication', seconds=120, provider_wide=True, message='Chiave non accettata.', action='Verifica di aver usato una chiave API del servizio selezionato.')
    elif code == 403:
        network = 'network settings' in text or 'country' in text or 'region' in text
        info.update(kind='network_denied' if network else 'permission', seconds=120, provider_wide=True,
                    message='Il servizio rifiuta la connessione dalla rete attuale.' if network else 'Accesso negato dal servizio.',
                    action='Controlla le restrizioni di rete e del tuo account sul sito del servizio.' if network else 'Verifica i permessi della chiave e del modello sul sito del servizio.')
    elif code == 404:
        info.update(kind='model_unavailable', seconds=180, message='Questo modello non è disponibile per il tuo account.',
                    action='Verifica il catalogo e scegli un modello attuale.')
        suggested = re.search(r'use models/(gemini-[a-zA-Z0-9_.-]{1,90})', message)
        if provider == 'gemini' and suggested:
            info['suggested_model'] = suggested.group(1)
            info['action'] = 'Il servizio consiglia '+suggested.group(1)+'. Selezionalo e prova una risposta.'
    elif code == 429:
        try:
            info['seconds'] = max(5, min(120, int(response.headers.get('Retry-After', 30))))
        except (ValueError, TypeError):
            info['seconds'] = 30
        info.update(kind='rate_limit', message='Limite di utilizzo raggiunto.', action='Attendi prima di riprovare.')
        if provider == 'openrouter' and 'free-models-per-day' in text:
            info.update(kind='daily_quota', seconds=900, provider_wide=True,
                        message='Quota giornaliera dei modelli gratuiti esaurita.',
                        action='Attendi il ripristino giornaliero oppure scegli un altro servizio. Cambiare modello gratuito o chiave dello stesso account non ripristina la quota.')
            metadata = detail.get('metadata', {})
            headers = metadata.get('headers', {}) if isinstance(metadata, dict) else {}
            try:
                reset = float(headers.get('X-RateLimit-Reset'))/1000
                if time.time() < reset <= time.time()+86400:
                    info['seconds'] = max(5, int(reset-time.time())+1)
                    info['reset_at'] = datetime.fromtimestamp(reset,timezone.utc).isoformat()
                    try:
                        local = datetime.fromtimestamp(reset, ZoneInfo('Europe/Rome'))
                        info['action'] = f'Quota nuovamente disponibile il {local:%d/%m alle %H:%M} (ora italiana). Nel frattempo puoi scegliere un altro servizio.'
                    except ZoneInfoNotFoundError:
                        pass
            except (TypeError, ValueError, OverflowError):
                pass
    elif code in (500, 502, 503, 504):
        info.update(kind='overloaded', message='Il servizio è temporaneamente sovraccarico o non disponibile.',
                    action='Attendi qualche momento oppure prova un altro modello.')
    elif code in (400, 422):
        info.update(kind='invalid_request', message='Il modello non accetta questa richiesta.', action='Verifica il modello selezionato e la sua compatibilità con AURA.')
    elif isinstance(error, (requests.Timeout, TimeoutError)):
        info.update(kind='timeout', message='Il servizio non ha risposto in tempo.', action='Riprova oppure scegli un modello più rapido.')
    elif isinstance(error, requests.ConnectionError):
        info.update(kind='connection', provider_wide=True, message='Impossibile collegarsi al servizio.',
                    action='Avvia il server se usi un modello locale; per i servizi online controlla la connessione.')
    elif isinstance(error, ValueError):
        info.update(kind='invalid_response', message='Il servizio ha restituito una risposta vuota, incompleta o non valida.', action='Prova di nuovo o scegli un altro modello.')
    return info
