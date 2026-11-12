"""Bounded streaming transports. Only final-answer text reaches the conversation."""
import json
import os
import time

import requests

from provider_errors import ProviderHTTPError
from provider_registry import PROVIDERS, base_url
from runtime_utils import provider_deadline, provider_timeout


class StreamIncompleteError(ValueError):
    pass


def stream_request(provider, model, messages, settings, options, schema):
    """Keep the same endpoints, privacy flags and generation budgets as normal replies."""
    info = PROVIDERS[provider]
    key = settings.get(info.get('key', '')) or os.getenv(str(info.get('key', '')).upper(), '')
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    temperature = options.get('temperature', .45)
    payload = {'model': model, 'messages': messages, 'max_tokens': options['max_tokens'],
               'temperature': temperature, 'stream': True}
    url = base_url(provider, settings) + '/chat/completions'
    protocol = 'chat'
    if provider == 'gemini':
        headers = {'Content-Type': 'application/json', 'x-goog-api-key': key}
        payload = {
            'systemInstruction': {'parts': [{'text': '\n'.join(m['content'] for m in messages if m['role'] == 'system')}]},
            'contents': [{'role': 'user' if m['role'] == 'user' else 'model', 'parts': [{'text': m['content']}]}
                         for m in messages if m['role'] != 'system'],
            'generationConfig': {'temperature': temperature, 'maxOutputTokens': options['max_tokens'],
                                 'responseMimeType': 'application/json',
                                 'responseSchema': {k: v for k, v in schema.items() if k != 'additionalProperties'}},
        }
        if model in {'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.8-flash'}:
            level = 'medium' if options.get('reasoning_effort') == 'medium' else ('low' if model == 'gemini-3.8-flash' else 'minimal')
            payload['generationConfig']['thinkingConfig'] = {'thinkingLevel': level}
        url = base_url(provider, settings) + f'/models/{model}:streamGenerateContent?alt=sse'
        protocol = 'gemini'
    elif provider == 'ollama':
        url = base_url(provider, settings) + '/api/chat'
        payload = {'model': model, 'messages': messages, 'stream': True, 'format': schema,
                   'options': {'temperature': temperature, 'num_predict': options['max_tokens']}}
        protocol = 'ollama'
    elif provider == 'anthropic':
        headers = {'Content-Type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01'}
        url = base_url(provider, settings) + '/messages'
        payload = {'model': model, 'system': '\n'.join(m['content'] for m in messages if m['role'] == 'system'),
                   'messages': [m for m in messages if m['role'] != 'system'], 'stream': True,
                   'max_tokens': options['max_tokens'], 'temperature': temperature}
        protocol = 'anthropic'
    elif provider in {'openai', 'xai'}:
        url = base_url(provider, settings) + '/responses'
        payload = {'model': model, 'input': messages, 'max_output_tokens': options['max_tokens'],
                   'store': False, 'stream': True,
                   'text': {'format': {'type': 'json_schema', 'name': 'aura_reply', 'schema': schema, 'strict': True}}}
        if provider == 'openai' and model.startswith(('gpt-4', 'chatgpt-4')):
            payload['temperature'] = temperature
        if provider == 'xai':
            payload.update(temperature=.7, top_p=.95)
        protocol = 'responses'
    elif provider == 'groq':
        payload['max_completion_tokens'] = payload.pop('max_tokens')
        if model in {'openai/gpt-oss-20b', 'qwen/qwen3.8-27b', 'openai/gpt-oss-120b'}:
            payload['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'assistant_reply', 'strict': True, 'schema': schema}}
            payload['reasoning_effort'] = options.get('reasoning_effort', 'low')
    elif provider == 'cerebras' and model in {'gpt-oss-120b', 'qwen-3.8-27b'}:
        payload['reasoning_effort'] = options.get('reasoning_effort', 'low')
    elif provider == 'openrouter':
        headers['X-Title'] = 'AURA'
    return url, headers, payload, protocol


def _check_deadline():
    deadline = provider_deadline.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('Tempo massimo provider raggiunto.')


def _events(response, protocol):
    """SSE has blank-line records and optional comments; Ollama uses NDJSON."""
    data, size = [], 0
    response.encoding = 'utf-8'
    for line in response.iter_lines(chunk_size=1, decode_unicode=True):
        _check_deadline()
        size += len(line)
        if size > 4 * 1024 * 1024 or len(line) > 1024 * 1024:
            raise ValueError('Risposta del servizio troppo grande')
        if protocol == 'ollama':
            if line.strip():
                yield json.loads(line)
        elif not line:
            if data:
                record = '\n'.join(data)
                data = []
                if record == '[DONE]':
                    return
                yield json.loads(record)
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
    if data:
        record = '\n'.join(data)
        if record != '[DONE]':
            yield json.loads(record)


def stream_provider(provider, model, messages, settings, options, schema, info):
    url, headers, payload, protocol = stream_request(provider, model, messages, settings, options, schema)
    finished = False
    with requests.Session() as session:
        session.trust_env = False
        with session.post(url, headers=headers, json=payload, timeout=provider_timeout(40),
                          stream=True, allow_redirects=False) as response:
            if not 200 <= response.status_code < 300:
                body = bytearray()
                for block in response.iter_content(4096):
                    body.extend(block)
                    if len(body) > 65536:
                        break
                try:
                    error = json.loads(body)
                except ValueError:
                    error = {}
                raise ProviderHTTPError(response, error)
            for event in _events(response, protocol):
                if event.get('error') or event.get('type') in {'error', 'response.failed'}:
                    error = event.get('error') or event.get('response', {}).get('error') or {}
                    code = error.get('code') or error.get('type') if isinstance(error, dict) else None
                    codes = {'rate_limit_error': 429, 'rate_limit_exceeded': 429, 'overloaded_error': 503,
                             'authentication_error': 401, 'permission_error': 403}
                    status = int(code) if str(code).isdigit() and 400 <= int(code) <= 599 else codes.get(code, 503)
                    failed = requests.Response()
                    failed.status_code = status
                    failed.headers.update(response.headers)
                    raise ProviderHTTPError(failed, {'error': error})
                resolved = event.get('model') or event.get('message', {}).get('model')
                if isinstance(resolved, str):
                    info['resolved_model'] = resolved[:160]
                usage = event.get('usage') or event.get('usageMetadata') or event.get('response', {}).get('usage')
                if isinstance(usage, dict):
                    info['usage'] = {k: v for k, v in usage.items() if type(v) is int and 0 <= v <= 10**9}
                text = ''
                if protocol == 'gemini':
                    candidates = event.get('candidates', [])
                    if candidates:
                        candidate = candidates[0]
                        reason = candidate.get('finishReason')
                        if reason and reason != 'STOP':
                            raise StreamIncompleteError('Risposta del servizio incompleta')
                        finished |= reason == 'STOP'
                        text = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []) if not p.get('thought'))
                elif protocol == 'ollama':
                    if event.get('done_reason') == 'length':
                        raise StreamIncompleteError('Limite di risposta raggiunto')
                    finished |= event.get('done') is True
                    text = event.get('message', {}).get('content', '')
                elif protocol == 'responses':
                    kind = event.get('type')
                    if kind == 'response.incomplete':
                        raise StreamIncompleteError('Limite di risposta raggiunto')
                    finished |= kind == 'response.completed'
                    if kind in {'response.output_text.delta', 'response.refusal.delta'}:
                        text = event.get('delta', '')
                elif protocol == 'anthropic':
                    if event.get('delta', {}).get('stop_reason') == 'max_tokens':
                        raise StreamIncompleteError('Limite di risposta raggiunto')
                    finished |= event.get('type') == 'message_stop'
                    if event.get('type') == 'content_block_start' and event.get('content_block', {}).get('type') == 'text':
                        text = event['content_block'].get('text', '')
                    if event.get('type') == 'content_block_delta' and event.get('delta', {}).get('type') == 'text_delta':
                        text = event['delta'].get('text', '')
                else:
                    choices = event.get('choices', [])
                    if choices:
                        choice = choices[0]
                        reason = choice.get('finish_reason')
                        if reason in {'length', 'error', 'content_filter'}:
                            raise StreamIncompleteError('Risposta del servizio incompleta')
                        finished |= reason is not None
                        text = choice.get('delta', {}).get('content') or choice.get('delta', {}).get('refusal') or ''
                if text:
                    if finished and info.get('stream_finished'):
                        raise ValueError('Testo dopo la fine della risposta')
                    yield text
                if finished:
                    info['stream_finished'] = True
            if not finished:
                raise StreamIncompleteError('Connessione interrotta prima della fine della risposta')
