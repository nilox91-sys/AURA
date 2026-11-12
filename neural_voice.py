"""Optional voices: isolated local Qwen and an explicitly configured Irodori Space."""
import base64
from contextlib import closing
import io
import json
import os
from pathlib import Path
import re
from threading import BoundedSemaphore
import time
from urllib.parse import quote
import wave

import requests
from anime_reading import anime_reading

BASE = Path(__file__).resolve().parent
SUPPORT = Path(os.getenv('LOCALAPPDATA', str(BASE))) / 'AURA' / 'voices'
QWEN_PYTHON = Path(os.getenv('AURA_QWEN_PYTHON', str(SUPPORT / 'qwen' / '.venv' / 'Scripts' / 'python.exe')))
QWEN_MODEL_DIR = Path(os.getenv('AURA_QWEN_MODEL_DIR', str(SUPPORT / 'qwen' / 'model')))
IRODORI_HOST = 'https://hugging-apps-irodori-tts-anime-demo.hf.space'
REFERENCE = BASE / 'static' / 'voices' / 'aura-irodori-reference.wav'
NEURAL_VOICE_REVISION = 'aura-stream-2'
CAPTION = '明るく親しみやすいアニメの少女の声。柔らかく澄んだ声で、自然な会話のように話す。落ち着いた速さで、少し楽しそうに、優しく微笑みながら。甲高くなりすぎない。'
MAX_AUDIO = 24 * 1024 * 1024
_irodori_slot = BoundedSemaphore(1)


class NeuralVoiceError(RuntimeError):
    """Contains only a fixed, safe user-facing message, never upstream details."""


def qwen_available():
    return (QWEN_PYTHON.is_file()
            and (QWEN_MODEL_DIR / 'model.safetensors').is_file()
            and (QWEN_MODEL_DIR / 'speech_tokenizer' / 'model.safetensors').is_file()
            and (QWEN_MODEL_DIR / 'aura-verified.json').is_file())


def validate_wav(audio):
    if not isinstance(audio, bytes) or not 44 <= len(audio) <= MAX_AUDIO:
        raise NeuralVoiceError('Il motore vocale non ha prodotto audio valido.')
    try:
        with wave.open(io.BytesIO(audio), 'rb') as stream:
            duration = stream.getnframes() / stream.getframerate()
            if stream.getnchannels() not in (1, 2) or not 0 < duration <= 180:
                raise ValueError('audio bounds')
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise NeuralVoiceError('Il motore vocale non ha prodotto audio valido.') from None
    return audio


from qwen_service import QwenService
qwen_service = QwenService(QWEN_PYTHON, BASE/'tools/qwen_stream_worker.py', QWEN_MODEL_DIR)


def stream_qwen_speech(text, style='anime', language='Italian'):
    if not isinstance(text, str) or not text.strip() or len(text)>600:
        raise NeuralVoiceError('Qwen legge fino a 600 caratteri per segmento.')
    if style not in {'anime','original'} or language not in {'Italian','Japanese','Korean'}:
        raise ValueError('Profilo Qwen non valido.')
    if not qwen_available():
        raise NeuralVoiceError('Qwen non è pronto. Esegui PREPARA_QWEN_TTS.bat nella cartella di AURA.')
    total=0
    try:
        with closing(qwen_service.stream({'text':text,'style':style,'language':language})) as events:
            for event in events:
                audio=base64.b64decode(event['audio'],validate=True)
                total+=len(audio)
                if total>MAX_AUDIO:
                    raise ValueError('audio size')
                yield validate_wav(audio)
    except (OSError, RuntimeError, TimeoutError, ValueError):
        raise NeuralVoiceError('Qwen non riesce a completare la frase. Riprova; il motore verrà riavviato.') from None


def generate_qwen_speech(text, style='anime', language='Italian'):
    output=io.BytesIO()
    with wave.open(output,'wb') as target:
        target.setparams((1,2,24000,0,'NONE','not compressed'))
        first=True
        for audio in stream_qwen_speech(text,style,language):
            with wave.open(io.BytesIO(audio),'rb') as source:
                if first:
                    target.setparams(source.getparams())
                    first=False
                elif (source.getnchannels(),source.getsampwidth(),source.getframerate()) != (target.getnchannels(),target.getsampwidth(),target.getframerate()):
                    raise NeuralVoiceError('Formato vocale non valido.')
                target.writeframes(source.readframes(source.getnframes()))
    return validate_wav(output.getvalue())


def _request(session, method, path, deadline, **kwargs):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NeuralVoiceError('Irodori ha impiegato troppo tempo. Riprova tra poco.')
    response = session.request(method, IRODORI_HOST + path, allow_redirects=False,
                               timeout=(min(10, remaining), min(30, remaining)), **kwargs)
    if response.status_code in (401, 403):
        response.close()
        raise NeuralVoiceError('Il token Hugging Face non è stato accettato. Controllalo nelle impostazioni.')
    if response.status_code == 429:
        response.close()
        raise NeuralVoiceError('Quota gratuita Hugging Face esaurita. Riprova dopo il rinnovo della quota o scegli una voce locale.')
    if not 200 <= response.status_code < 300:
        response.close()
        raise NeuralVoiceError('La demo Irodori non è disponibile in questo momento.')
    return response


def _read_limited(response, limit, deadline):
    chunks, count = [], 0
    try:
        for block in response.iter_content(65536):
            count += len(block)
            if count > limit or time.monotonic() > deadline:
                raise NeuralVoiceError('Risposta del servizio vocale non valida o troppo lenta.')
            chunks.append(block)
        return b''.join(chunks)
    finally:
        response.close()


def _result_file(response, deadline):
    event, data, count = '', [], 0
    try:
        for raw in response.iter_lines(chunk_size=1024):
            count += len(raw)
            if count > 512 * 1024 or time.monotonic() > deadline:
                raise NeuralVoiceError('Irodori ha impiegato troppo tempo. Riprova tra poco.')
            line = raw.decode('utf-8')
            if line.startswith('event:'):
                event = line[6:].strip()
            elif line.startswith('data:'):
                data.append(line[5:].lstrip())
            elif not line and data:
                payload = '\n'.join(data)
                data = []
                if event == 'error':
                    if any(word in payload.lower() for word in ('quota', 'limit', 'zerogpu')):
                        raise NeuralVoiceError('Quota gratuita Hugging Face esaurita. Riprova dopo il rinnovo della quota o scegli una voce locale.')
                    raise NeuralVoiceError('La demo Irodori non riesce a generare questa frase.')
                if event == 'complete':
                    values = json.loads(payload)
                    if not isinstance(values, list) or not values or not isinstance(values[0], dict):
                        break
                    path = values[0].get('path')
                    if isinstance(path, str) and path.startswith('/tmp/gradio/') and len(path) < 1024:
                        return '/gradio_api/file=' + quote(path, safe='/')
                    break
        raise NeuralVoiceError('Il servizio vocale non ha restituito un campione valido.')
    finally:
        response.close()


def generate_irodori_speech(text, token, reading='kana', rate_percent=0):
    if not isinstance(token, str) or not re.fullmatch(r'hf_[A-Za-z0-9]{8,500}', token):
        raise NeuralVoiceError('Per Irodori inserisci un token personale Hugging Face nelle impostazioni. L’accesso nel browser non collega automaticamente AURA.')
    if not isinstance(text, str) or not text.strip() or len(text) > 600:
        raise NeuralVoiceError('Irodori legge fino a 600 caratteri per volta. Prova una risposta più breve.')
    if reading not in {'kana', 'original'} or type(rate_percent) is not int or not -20 <= rate_percent <= 20:
        raise ValueError('Impostazione Irodori non valida.')
    prepared = anime_reading(text) if reading == 'kana' else text
    if len(prepared) > 350:
        raise NeuralVoiceError('La lettura anime è troppo lunga. Accorcia la frase o scegli Qwen.')
    if not _irodori_slot.acquire(timeout=1):
        raise NeuralVoiceError('Irodori sta preparando un’altra frase. Riprova tra poco.')
    try:
        deadline = time.monotonic() + 150
        with requests.Session() as session:
            session.trust_env = False
            session.headers.update(Authorization='Bearer ' + token, **{'User-Agent':'AURA-voices/1.5'})
            with REFERENCE.open('rb') as source:
                response = _request(session, 'POST', '/gradio_api/upload', deadline,
                                    files={'files':('aura-synthetic-reference.wav',source,'audio/wav')})
                uploaded = json.loads(_read_limited(response, 8192, deadline))
            if (not isinstance(uploaded, list) or len(uploaded) != 1 or not isinstance(uploaded[0], str)
                    or not uploaded[0].startswith('/tmp/gradio/') or len(uploaded[0]) > 1024):
                raise NeuralVoiceError('Il servizio non ha accettato il riferimento vocale.')
            reference = {'path': uploaded[0], 'meta': {'_type':'gradio.FileData'}, 'orig_name':'aura-synthetic-reference.wav'}
            parameters = [prepared,CAPTION,[reference],40,'20261111',1/(1+rate_percent/100),'',3.5,4,5,'linear',-1,0.5,1]
            response = _request(session, 'POST', '/gradio_api/call/generate', deadline, json={'data':parameters})
            event_id = json.loads(_read_limited(response, 8192, deadline)).get('event_id')
            if not isinstance(event_id, str) or not re.fullmatch('[a-fA-F0-9]{16,64}', event_id):
                raise NeuralVoiceError('Il servizio non ha avviato la sintesi.')
            response = _request(session, 'GET', '/gradio_api/call/generate/' + event_id, deadline, stream=True)
            output = _result_file(response, deadline)
            response = _request(session, 'GET', output, deadline, stream=True)
            return validate_wav(_read_limited(response, MAX_AUDIO, deadline))
    except NeuralVoiceError:
        raise
    except (requests.RequestException, OSError, ValueError, TypeError, KeyError):
        raise NeuralVoiceError('Irodori non è disponibile in questo momento. Le altre voci restano selezionabili.') from None
    finally:
        _irodori_slot.release()
