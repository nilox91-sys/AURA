"""Optional, project-local Kokoro setup. Run explicitly, never while opening a page."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

BASE = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Prepara la voce locale di AURA')
    parser.add_argument('--from-dir', type=Path, help='Riusa file ufficiali già scaricati e verificati')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Questa procedura guidata prepara Windows con Python 3.13.')
    support = Path(os.environ['LOCALAPPDATA']) / 'AURA' / 'voices' / 'kokoro'
    environment = support / '.venv'
    interpreter = environment / 'Scripts' / 'python.exe'
    if not interpreter.is_file():
        print('Preparazione ambiente vocale separato (Python 3.13)…', flush=True)
        subprocess.run(['py', '-3.13', '-m', 'venv', str(environment)], check=True)
    subprocess.run([str(interpreter), '-m', 'pip', 'install', '--disable-pip-version-check',
                    '--only-binary=:all:', '-r', str(BASE / 'requirements-voice.lock.txt')], check=True)
    directory = (support / 'model').resolve()
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((BASE / 'voice-model-manifest.json').read_text(encoding='utf-8'))
    for item in manifest:
        destination = (directory / Path(item['path']).name).resolve()
        if destination.parent != directory:
            raise RuntimeError('Percorso modello non valido.')
        if destination.is_file() and digest(destination) == item['sha256']:
            continue
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                temporary = Path(output.name)
                existing = args.from_dir / destination.name if args.from_dir else None
                if existing and existing.is_file():
                    with existing.open('rb') as source:
                        shutil.copyfileobj(source, output)
                else:
                    print('Download del modello vocale: ' + destination.name, flush=True)
                    request = urllib.request.Request(item['url'], headers={'User-Agent':'AURA-local-voice/1.4'})
                    with urllib.request.urlopen(request, timeout=30) as source:
                        shutil.copyfileobj(source, output)
            if temporary.stat().st_size != item['bytes'] or digest(temporary) != item['sha256']:
                raise RuntimeError('Controllo di integrità del modello fallito.')
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
    print('Voce locale pronta. Avvia AURA e scegli Hiyori · anime locale nelle impostazioni.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        print('Preparazione non completata. Servono Python 3.13 e Internet. Puoi riprovare senza perdere i dati di AURA.', file=sys.stderr)
        sys.exit(1)
