"""Optional local voice shaping. Audio stays in memory; no shell or voice cloning."""
from functools import lru_cache
import os
import shutil
import subprocess
from threading import BoundedSemaphore

TIMBRE_REVISION = 'hiyori-soft-1'
TIMBRES = {'young': (1.16, 1.12), 'anime': (1.23, 1.17)}
_workers = BoundedSemaphore(2)


class VoiceTimbreError(RuntimeError):
    pass


def _process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


@lru_cache(maxsize=1)
def timbre_available():
    executable = shutil.which('ffmpeg')
    if not executable:
        return False
    try:
        result = subprocess.run([executable, '-hide_banner', '-filters'],
            capture_output=True, timeout=3, check=True, **_process_options())
        return b'rubberband' in result.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def timbre_filter(effect):
    if effect not in TIMBRES:
        raise ValueError('Timbro non valido.')
    pitch, resonance = TIMBRES[effect]
    # Separate resonance and fundamental pitch: retain the chosen anime pitch
    # with a milder resonance shift. Compensate speed to preserve lip timing.
    return (
        f'aresample=48000,asetrate={round(48000 * resonance)},aresample=48000,'
        f'rubberband=tempo={1 / resonance:.9f}:pitch={pitch / resonance:.9f}:'
        'formant=preserved:transients=mixed:detector=soft:phase=laminar:'
        'window=standard:smoothing=on,'
        'highpass=f=80,equalizer=f=400:t=q:w=0.7:g=-1.2,'
        'deesser=i=0.12:m=0.35:f=0.5,lowpass=f=10500,'
        'alimiter=limit=0.95:level=false'
    )


def apply_voice_timbre(audio, effect='none'):
    if effect == 'none':
        return audio
    filters = timbre_filter(effect)
    if not timbre_available():
        raise VoiceTimbreError('Affinamento del timbro non disponibile.')
    if not isinstance(audio, bytes) or not audio or len(audio) > 8 * 1024 * 1024:
        raise VoiceTimbreError('Audio non valido.')
    if not _workers.acquire(timeout=3):
        raise VoiceTimbreError('Voce occupata, riprova tra poco.')
    try:
        result = subprocess.run([
            shutil.which('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-filter_threads', '1', '-protocol_whitelist', 'pipe', '-i', 'pipe:0',
            '-vn', '-af', filters, '-map_metadata', '-1', '-ac', '1', '-ar', '24000',
            '-c:a', 'libmp3lame', '-b:a', '64k', '-write_xing', '0', '-f', 'mp3', 'pipe:1',
        ], input=audio, capture_output=True, timeout=12, check=True, **_process_options())
        if not result.stdout or len(result.stdout) > 8 * 1024 * 1024:
            raise VoiceTimbreError('Il timbro non ha prodotto audio valido.')
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        raise VoiceTimbreError('Affinamento del timbro temporaneamente non disponibile.') from None
    finally:
        _workers.release()
