"""Isolated local synthesis: the main app keeps its existing Python environment."""
from pathlib import Path
import json
import os
import subprocess
from threading import BoundedSemaphore

BASE = Path(__file__).resolve().parent
SUPPORT = Path(os.getenv('LOCALAPPDATA', str(BASE))) / 'AURA' / 'voices' / 'kokoro'
MODEL_DIR = Path(os.getenv('AURA_LOCAL_VOICE_MODEL_DIR', str(SUPPORT / 'model')))
VOICE_PYTHON = Path(os.getenv('AURA_LOCAL_VOICE_PYTHON',
    str(SUPPORT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))))
LOCAL_VOICE_REVISION = 'kokoro-hiyori-1'
STYLES = {'hiyori', 'hiyori_soft', 'sara'}
_slot = BoundedSemaphore(1)


class LocalVoiceError(RuntimeError):
    pass


def local_voice_available():
    return (VOICE_PYTHON.is_file()
            and (MODEL_DIR / 'kokoro-v1.0.onnx').is_file()
            and (MODEL_DIR / 'voices-v1.0.bin').is_file())


def generate_local_speech(text, style='hiyori', rate_percent=0, emotion='normale'):
    if style not in STYLES or not isinstance(text, str) or not text.strip() or len(text) > 2500:
        raise ValueError('Profilo o testo vocale non valido.')
    if type(rate_percent) is not int or not -20 <= rate_percent <= 20:
        raise ValueError('Velocità non valida.')
    if not local_voice_available():
        raise LocalVoiceError('La voce locale non è pronta. Usa la preparazione della voce locale.')
    if not _slot.acquire(timeout=3):
        raise LocalVoiceError('Voce locale occupata, riprova tra poco.')
    try:
        payload = json.dumps({'text': text, 'style': style, 'rate_percent': rate_percent,
                              'emotion': emotion}, ensure_ascii=False).encode('utf-8')
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        allowed = {'PATH','SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT','TEMP','TMP',
                   'USERPROFILE','LOCALAPPDATA','APPDATA','PROGRAMFILES','PROGRAMFILES(X86)',
                   'PROGRAMDATA','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS'}
        environment = {key:value for key,value in os.environ.items() if key.upper() in allowed}
        environment.update(PYTHONUTF8='1', AURA_LOCAL_VOICE_MODEL_DIR=str(MODEL_DIR))
        result = subprocess.run([str(VOICE_PYTHON), str(BASE / 'tools' / 'local_voice_worker.py')],
            input=payload, capture_output=True, timeout=90, check=True, cwd=BASE, env=environment, **options)
        audio = result.stdout
        if len(audio) < 44 or len(audio) > 24 * 1024 * 1024 or audio[:4] != b'RIFF' or audio[8:12] != b'WAVE':
            raise LocalVoiceError('Il motore locale non ha prodotto audio valido.')
        return audio
    except (OSError, subprocess.SubprocessError):
        raise LocalVoiceError('Sintesi locale temporaneamente non disponibile.') from None
    finally:
        _slot.release()
