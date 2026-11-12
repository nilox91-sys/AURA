"""Explicit Qwen setup in local app data, away from the OneDrive project."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
REPO = 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'
REVISION = '5d83992436eae1d760afd27aff78a71d676296fc'
CHECKS = {
    'model.safetensors':'180b3b10eb1c9f1b4db7806d5475bae3071c0243c299d49926bab1da3b6946f6',
    'speech_tokenizer/model.safetensors':'836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258',
}


def download_and_verify(directory):
    from huggingface_hub import snapshot_download
    ready = all((directory/relative).is_file() for relative in CHECKS)
    required = ['config.json','tokenizer_config.json','vocab.json','merges.txt',
                'preprocessor_config.json','speech_tokenizer/config.json',
                'speech_tokenizer/preprocessor_config.json']
    if not ready or not all((directory/relative).is_file() for relative in required):
        snapshot_download(REPO, revision=REVISION, local_dir=directory,
            allow_patterns=['*.json','*.txt','*.safetensors'], token=False, max_workers=2)
    for relative, expected in CHECKS.items():
        with (directory/relative).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != expected:
                raise RuntimeError('Verifica del modello non riuscita.')
    (directory/'aura-verified.json').write_text(json.dumps({'repo':REPO,'revision':REVISION,'sha256':CHECKS},indent=2),encoding='utf-8')


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--download':
        download_and_verify(Path(sys.argv[2])); return
    if os.name != 'nt':
        raise RuntimeError('Questa preparazione è dedicata a Windows con Python 3.13.')
    support = Path(os.environ['LOCALAPPDATA'])/'AURA'/'voices'/'qwen'
    interpreter = support/'.venv'/'Scripts'/'python.exe'
    if not interpreter.is_file():
        subprocess.run(['py','-3.13','-m','venv',str(support/'.venv')],check=True)
    print('Preparazione delle librerie Qwen. Il primo download richiede alcuni GB.',flush=True)
    subprocess.run([str(interpreter),'-m','pip','install','--disable-pip-version-check',
        'torch==2.10.0','torchaudio==2.10.0','--index-url','https://download.pytorch.org/whl/cu128'],check=True)
    lock = BASE/'requirements-qwen.lock.txt'
    packages = ['-r',str(lock)] if lock.is_file() else ['qwen-tts==0.1.1']
    subprocess.run([str(interpreter),'-m','pip','install','--disable-pip-version-check',*packages],check=True)
    subprocess.run([str(interpreter),str(Path(__file__).resolve()),'--download',str(support/'model')],check=True)
    print('Qwen pronto. Avvia AURA e scegli Qwen3-TTS nelle impostazioni vocali.',flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        print('Preparazione Qwen non completata. Servono Python 3.13, Internet e spazio per le librerie e i modelli. Puoi riprovare senza perdere le impostazioni di AURA.',file=sys.stderr)
        sys.exit(1)
