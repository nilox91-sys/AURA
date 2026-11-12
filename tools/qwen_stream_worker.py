"""Persistent offline voice process. Bounded JSON lines in/out; no credentials."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time

BASE = Path(__file__).resolve().parents[1]
OUTPUT = sys.stdout
TRANSCRIPT = 'やっほー、アウラだよ。今日は何を作ろうか？面白いアイデアがあったら、聞かせてね。一緒に少しずつ形にしていこう。'


def send(event):
    OUTPUT.write(json.dumps(event, ensure_ascii=True) + '\n')
    OUTPUT.flush()


def main():
    with contextlib.redirect_stdout(sys.stderr):
        import torch  # Load Windows DLLs first.
        import numpy as np
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel
        torch.set_num_threads(4)
        device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        accelerated = False
        try:
            if device == 'cpu':
                raise ImportError('CPU baseline')
            from faster_qwen3_tts import FasterQwen3TTS
            model = FasterQwen3TTS.from_pretrained(os.environ['AURA_QWEN_MODEL_DIR'],
                device='cuda', dtype=torch.bfloat16, max_seq_len=2048, local_files_only=True)
            model.warmup(prefill_len=100)
            accelerated = True
        except ImportError:
            model = Qwen3TTSModel.from_pretrained(os.environ['AURA_QWEN_MODEL_DIR'],
                device_map=device, dtype=torch.bfloat16 if device != 'cpu' else torch.float32,
                attn_implementation='sdpa', local_files_only=True)
        prompts = {}
        base_model = model.model if accelerated else model

        def prompt(style):
            if style not in prompts:
                reference = BASE/'static/voices'/('aura-irodori-japanese.wav' if style == 'anime' else 'aura-irodori-reference.wav')
                prompts[style] = base_model.create_voice_clone_prompt(ref_audio=str(reference),
                    ref_text=TRANSCRIPT if style == 'anime' else None, x_vector_only_mode=style == 'original')
            return prompts[style]

        prompt('anime')
        if accelerated:
            # Prime codec kernels too: CUDA graphs alone leave a slow first decode.
            for _ in model.generate_voice_clone_streaming(text='Ciao.', language='Italian',
                    voice_clone_prompt=prompt('anime'), non_streaming_mode=True,
                    max_new_tokens=120, chunk_size=8):
                pass
        send({'event':'ready', 'accelerated':accelerated, 'device':device})
        while True:
            raw = sys.stdin.buffer.readline(65537)
            if not raw:
                break
            if len(raw) > 65536 or not raw.endswith(b'\n'):
                raise ValueError('frame')
            try:
                request = json.loads(raw)
                text, style, language = request.get('text'), request.get('style'), request.get('language')
                if not isinstance(text,str) or not text.strip() or len(text)>600 or style not in {'anime','original'} or language not in {'Italian','Japanese','Korean'}:
                    raise ValueError('request')
                started = time.monotonic()
                options = dict(text=text, language=language, voice_clone_prompt=prompt(style),
                               non_streaming_mode=True, max_new_tokens=min(1500, max(120, len(text)*6)))
                if accelerated:
                    chunks = model.generate_voice_clone_streaming(**options, chunk_size=8)
                else:
                    waves, sr = model.generate_voice_clone(**options)
                    chunks = ((waves[0], sr, {}),)
                duration = 0
                for audio, sample_rate, _ in chunks:
                    audio = np.asarray(audio, dtype=np.float32)
                    duration += len(audio)/sample_rate
                    if not np.isfinite(audio).all() or duration > 150:
                        raise ValueError('audio')
                    if not audio.size:
                        continue
                    output = io.BytesIO()
                    sf.write(output, audio, sample_rate, format='WAV', subtype='PCM_16')
                    send({'event':'audio', 'audio':base64.b64encode(output.getvalue()).decode('ascii')})
                if duration <= 0:
                    raise ValueError('empty audio')
                send({'event':'done', 'seconds':round(time.monotonic()-started,3)})
            except Exception as error:
                print('Qwen request failed: '+type(error).__name__, file=sys.stderr)
                send({'event':'error'})


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Qwen worker failed: '+type(error).__name__, file=sys.stderr)
        sys.exit(1)
