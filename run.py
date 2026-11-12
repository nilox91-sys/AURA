"""Bootstrap a project-local Python environment and start the local assistant."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser

BASE = Path(__file__).resolve().parent
ENV = BASE / '.venv'
ENV_PYTHON = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def dependencies_match(requirements):
    for line in requirements.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.strip().split('==', 1)
        try:
            if importlib.metadata.version(name) != version:
                return False
        except importlib.metadata.PackageNotFoundError:
            return False
    return True


def prepare_environment():
    if sys.version_info < (3, 10):
        raise RuntimeError('Installa Python 3.10 o successivo e riavvia Aura.')
    if not ENV_PYTHON.exists():
        print('Preparazione ambiente Aura (solo al primo avvio)…', flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    if Path(sys.executable).resolve() != ENV_PYTHON.resolve():
        return subprocess.call([str(ENV_PYTHON), str(BASE / 'run.py'), *sys.argv[1:]], cwd=BASE)
    requirements = BASE / 'requirements.lock.txt'
    if not requirements.exists():
        requirements = BASE / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = ENV / 'requirements.sha256'
    if not dependencies_match(requirements):
        print('Aggiornamento delle librerie del progetto…', flush=True)
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], cwd=BASE)
    if not stamp.exists() or stamp.read_text().strip() != fingerprint:
        stamp.write_text(fingerprint)
    return None


def server_status(url):
    try:
        with urllib.request.urlopen(url + 'api/status', timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def main():
    parser = argparse.ArgumentParser(description='Aura AI · assistente locale')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true', help='Controlla ambiente e dipendenze senza avviare il server')
    parser.add_argument('--port', type=int, default=5001)
    parser.add_argument('--reset-github-login',action='store_true',help='Disattiva il blocco GitHub per recuperare l’accesso locale; riavvia AURA dopo il ripristino')
    args = parser.parse_args()
    if args.reset_github_login:
        from dotenv import load_dotenv
        load_dotenv(BASE / '.env')
        path = Path(os.getenv('JARVIS_DATA_DIR',str(BASE))) / 'settings.json'
        if path.exists():
            from settings_store import SettingsManager
            values = json.loads(path.read_text(encoding='utf-8-sig'))
            values['github_require_login'] = False
            manager = SettingsManager(path,values)
            manager.update({'github_require_login':False})
        print('Accesso obbligatorio disattivato. Riavvia AURA per applicare il ripristino.')
        return 0
    if not 1024 <= args.port <= 65535:
        parser.error('La porta deve essere compresa tra 1024 e 65535.')
    result = prepare_environment()
    if result is not None:
        return result
    if args.check:
        print('Ambiente Aura pronto. Dipendenze verificate. Nessun servizio remoto contattato.')
        from timbre_engine import timbre_available
        print('Effetti vocali opzionali disponibili.' if timbre_available() else 'Voce standard disponibile; effetti vocali opzionali non installati.')
        from local_voice import local_voice_available
        print('Voce locale Kokoro pronta.' if local_voice_available() else 'Voce locale opzionale: usa PREPARA_VOCE_LOCALE.bat per aggiungerla.')
        from neural_voice import qwen_available
        print('Voce Qwen pronta.' if qwen_available() else 'Voce Qwen opzionale: usa PREPARA_QWEN_TTS.bat per aggiungerla.')
        return 0
    url = f'http://127.0.0.1:{args.port}/'
    current = server_status(url)
    if current and current.get('app_id') in ('aura-local', 'jarvis-local'):
        if current.get('app_version') != '2.0.0':
            raise RuntimeError('È ancora attiva una versione precedente di Aura. Chiudi la sua finestra e riavvia questo BAT.')
        expected_project = hashlib.sha256(str(BASE).casefold().encode()).hexdigest()[:16]
        if current.get('project_id') != expected_project:
            raise RuntimeError('Un’altra copia di Aura usa questa porta. Chiudila oppure avvia con --port 5010.')
        print(f'Aura è già attivo: {url}')
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    if current:
        raise RuntimeError(f'La porta {args.port} è già occupata. Chiudi la vecchia finestra di Aura o usa --port.')
    environment = dict(os.environ, JARVIS_PORT=str(args.port), PYTHONUTF8='1')
    process = subprocess.Popen([sys.executable, str(BASE / 'app.py')], cwd=BASE, env=environment)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Il server non è partito. Controlla il messaggio mostrato sopra.')
            current = server_status(url)
            if current and current.get('app_id') in ('aura-local', 'jarvis-local'):
                print(f'Aura pronto: {url}\nLascia questa finestra aperta. Ctrl+C per arrestare.', flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return process.wait()
            time.sleep(0.3)
        raise RuntimeError('Il server non ha risposto entro 30 secondi.')
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nAura arrestato.')
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'Avvio non riuscito: {error}', file=sys.stderr)
        sys.exit(1)
