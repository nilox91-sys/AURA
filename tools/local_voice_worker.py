"""One bounded synthesis job. JSON from stdin, PCM WAV to stdout; no network."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import wave

BASE = Path(__file__).resolve().parents[1]


def main():
    request = json.loads(sys.stdin.buffer.read(65537).decode('utf-8'))
    text = request.get('text')
    style = request.get('style', 'hiyori')
    rate = request.get('rate_percent', 0)
    if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 2500
            or style not in {'hiyori', 'hiyori_soft', 'sara'}
            or type(rate) is not int or not -20 <= rate <= 20):
        raise ValueError('Invalid synthesis request')
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import onnxruntime as rt
        from kokoro_onnx import Kokoro
        rt.disable_telemetry_events()
        options = rt.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        directory = Path(os.getenv('AURA_LOCAL_VOICE_MODEL_DIR', str(BASE / 'voice_models' / 'kokoro')))
        session = rt.InferenceSession(str(directory / 'kokoro-v1.0.onnx'),
            sess_options=options, providers=['CPUExecutionProvider'])
        engine = Kokoro.from_session(session, str(directory / 'voices-v1.0.bin'))
        sara = engine.get_voice_style('if_sara')
        if style == 'sara':
            voice = sara
        else:
            alpha = engine.get_voice_style('jf_alpha')
            weight = 0.65 if style == 'hiyori' else 0.35
            voice = (1 - weight) * sara + weight * alpha
        # The timbre comes from native speaker styles. No pitch/formant processing.
        mood = {'felice': .01, 'sorpresa': .01, 'triste': -.02}.get(request.get('emotion'), 0)
        speed = max(.8, min(1.2, 1 + rate / 100 + mood))
        samples, sample_rate = engine.create(text, voice=voice, speed=speed,
            lang='it', continuous=False)
        samples = np.asarray(samples, dtype=np.float32)
        if not len(samples) or not np.isfinite(samples).all():
            raise ValueError('Invalid audio')
        peak = float(np.max(np.abs(samples)))
        if peak > .98:
            samples *= .98 / peak
        pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
        output = io.BytesIO()
        with wave.open(output, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(sample_rate)
            stream.writeframes(pcm)
    sys.stdout.buffer.write(output.getvalue())


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Do not expose spoken text, machine paths or model diagnostics to the caller.
        sys.exit(1)
