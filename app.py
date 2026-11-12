from threading import Thread
from flask import Response, stream_with_context
from neural_voice import stream_qwen_speech, qwen_service
import os
import base64
import io
import re
import json
import logging
import asyncio
import hashlib
import sqlite3
import requests
import time
from threading import Lock
from settings_store import SettingsManager, SECRET_KEYS
from preferences import EXTRA_DEFAULTS
from provider_registry import PROVIDERS, visible_providers, visible_models
from runtime_utils import cache_audio, provider_deadline
from dialect_engine import prepare_tts_text, dialect_metadata
from voice_profile import voice_prosody, VOICE_REVISION
from timbre_engine import apply_voice_timbre, TIMBRE_REVISION, timbre_available
from local_voice import generate_local_speech, local_voice_available, LOCAL_VOICE_REVISION
from neural_voice import generate_qwen_speech, generate_irodori_speech, qwen_available, NeuralVoiceError, NEURAL_VOICE_REVISION
from typing import Dict, Any, List, Tuple, Optional
from flask import Flask, render_template, request, jsonify, send_file
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
import edge_tts

# ── Caricamento variabili d'ambiente ──────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── Logging Configuration ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("Aura.Core")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.getenv("JARVIS_DATA_DIR", BASE_DIR))
AUDIO_CACHE_DIR = os.path.join(DATA_DIR, "audio_cache")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
DIALECTS_FILE = os.path.join(BASE_DIR, "dialects.json")
PHONETICS_FILE = os.path.join(BASE_DIR, "phonetics.json")
DB_FILE = os.path.join(DATA_DIR, "nexus_db.sqlite")
chat_lock = Lock()

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# ── 1. Database Manager ────────────────────────────────────────────────────────
class DatabaseManager:
    """Gestisce la persistenza della chat con SQLite in modo thread-safe."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=15)

    def init_db(self) -> None:
        try:
            conn = self._get_connection()
            try:
                with conn:
                    c = conn.cursor()
                    c.execute('''CREATE TABLE IF NOT EXISTS chat_history
                                 (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)''')
            finally:
                conn.close()
            logger.info("💾 Database SQLite inizializzato correttamente.")
        except Exception as e:
            logger.error(f"❌ Errore inizializzazione DB: {e}")

    def get_chat_history(self, limit: int = 30) -> List[Dict[str, str]]:
        """Recupera gli ultimi N messaggi in ordine cronologico."""
        try:
            conn = self._get_connection()
            try:
                c = conn.cursor()
                query = """
                    SELECT role, content FROM (
                        SELECT id, role, content FROM chat_history ORDER BY id DESC LIMIT ?
                    ) ORDER BY id ASC
                """
                c.execute(query, (limit,))
                rows = c.fetchall()
                return [{"role": r[0], "content": r[1]} for r in rows]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"❌ Errore lettura storico chat dal DB: {e}")
            return []

    def save_chat_message(self, role: str, content: str) -> None:
        try:
            conn = self._get_connection()
            try:
                with conn:
                    c = conn.cursor()
                    c.execute("INSERT INTO chat_history (role, content) VALUES (?, ?)", (role, content))
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"❌ Errore salvataggio messaggio nel DB: {e}")

    def clear_chat_history(self) -> None:
        try:
            conn = self._get_connection()
            try:
                with conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM chat_history")
            finally:
                conn.close()
            logger.info("🧹 Storico chat azzerato dal DB.")
        except Exception as e:
            logger.error(f"❌ Errore azzeramento DB: {e}")
            raise e

    def get_message_count(self) -> int:
        """Restituisce il numero di messaggi memorizzati senza esporne il contenuto."""
        try:
            conn = self._get_connection()
            try:
                row = conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Errore conteggio memoria: {e}")
            return 0

db_manager = DatabaseManager(DB_FILE)

# ── 2. Settings Manager ────────────────────────────────────────────────────────
DEFAULT_SETTINGS: Dict[str, Any] = {
    "schema_version": 11,
    "tts_engine": "edge",
    "local_voice_style": "hiyori",
    "qwen_voice_style": "anime",
    "irodori_reading": "kana",
    "avatar_model": "hiyori",
    "assistant_name": "AURA",
    "user_name":      "Signore",
    "model":          "openrouter:openrouter/free",
    "ai_mode":        "balanced",
    "allow_fallback": False,
    "context_turns":  12,
    "context_chars":  16000,
    "max_response_tokens": 2048,
    "hf_api_key":     "",
    "groq_api_key":   "",
    "gemini_api_key": "",
    "openrouter_api_key": "",
    "ollama_host":    "http://localhost:11434",
    "elite_model":    "none",
    "use_kawaii_pitch": False,
    "voice_name":     "it-IT-ElsaNeural",
    "voice_pitch_hz": 0,
    "voice_rate_percent": 0,
    "voice_character": "soft",
    "voice_effect": "none",
    "personality_profile": "cozy_nerd",
    "nerd_intensity": "balanced",
    "response_style": "balanced",
    "proactive_mode": True,
    "wake_enabled":   True,
    "dialect":        "napoletano",
    "dialect_intensity": "balanced",
    "pronunciation_mode": "natural",
    "wake_word":      "ehi aura"
}

DEFAULT_SETTINGS.update(EXTRA_DEFAULTS)
settings_manager = SettingsManager(SETTINGS_FILE, DEFAULT_SETTINGS)

def get_active_chat_history(limit: int = 30) -> List[Dict[str, str]]:
    """Return recent messages without silently hiding parts of the conversation."""
    return db_manager.get_chat_history(limit=max(1, min(limit, 200)))

# ── 3. Dialects & Phonetics Loaders ────────────────────────────────────────────
def load_json_dict(filepath: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Errore caricamento {filepath}: {e}")
    return fallback

DIZIONARIO_DIALETTI = load_json_dict(
    DIALECTS_FILE,
    {"standard": "Esprimiti in italiano naturale, chiaro e preciso."}
)

DIZIONARIO_FONETICO = load_json_dict(PHONETICS_FILE, {})

def applica_pronuncia_perfetta(testo: str, dialect: str = 'standard', mode=None) -> str:
    selected = mode or settings_manager.get('pronunciation_mode', 'natural')
    return prepare_tts_text(testo, dialect, selected, DIZIONARIO_FONETICO)

# ── 4. AI orchestration ──────────────────────────────────────────────────────
from ai_engine import LLMEngine, FREE_PROVIDER_MODELS, generation_info, generation_options, IncompleteResponseError
LLMEngine.dialects = DIZIONARIO_DIALETTI
ai_check_lock = Lock()

# ── 5. TTS Engine (Edge-TTS & Elite HF TTS) ──────────────────────────────────
class TTSEngine:
    @staticmethod
    def _run_async(coro):
        """Esegue una coroutine async in modo sicuro anche se è già attivo un event loop."""
        # Flask runs sync endpoints in worker threads without a nested event loop.
        return asyncio.run(coro)

    @classmethod
    async def _tts_generate_async(
        cls,
        text: str,
        emotion: str,
        kawaii: bool,
        elite_model: Optional[str],
        dialect: str,
        voice_name: str,
        base_pitch_hz: int,
        base_rate_percent: int,
        voice_character: str = 'soft',
    ) -> bytes:
        # Se è specificato un modello Elite via HF
        hf_key = settings_manager.get("hf_api_key") or os.getenv("HF_API_KEY")
        if elite_model and elite_model != "none" and hf_key:
            try:
                logger.info(f"🎙️ Generazione TTS Elite HF: {elite_model}")
                client = InferenceClient(api_key=hf_key, timeout=20)
                return await asyncio.to_thread(client.text_to_speech, text, model=elite_model)
            except Exception as e:
                logger.warning("Elite TTS fallito (%s). Ripiego su Edge-TTS.", type(e).__name__)

        # Parametri Edge-TTS
        voice = "ja-JP-NanamiNeural" if dialect == "giaponese" else (voice_name or "it-IT-ElsaNeural")

        prosody = voice_prosody(emotion, base_pitch_hz, base_rate_percent, voice_character, kawaii)
        communicator = edge_tts.Communicate(text, voice, **prosody,
                                            connect_timeout=5, receive_timeout=20)
        audio_bytes = b""
        async for chunk in communicator.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        return audio_bytes

    @classmethod
    def generate_speech(
        cls,
        text: str,
        emotion: str,
        kawaii: bool,
        elite_model: Optional[str],
        dialect: str,
        voice_name: str,
        base_pitch_hz: int,
        base_rate_percent: int,
        voice_character: str = 'soft',
    ) -> bytes:
        return cls._run_async(
            asyncio.wait_for(cls._tts_generate_async(
                text,
                emotion,
                kawaii,
                elite_model,
                dialect,
                voice_name,
                base_pitch_hz,
                base_rate_percent,
                voice_character,
            ), timeout=30)
        )

# ── 6. Inizializzazione Flask App ─────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1", "[::1]"]

@app.before_request
def protect_local_api():
    if request.path.startswith('/api/'):
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            return jsonify(status='error', error='Origine della richiesta non consentita.'), 403
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(status='error', error='Richiesta esterna non consentita.'), 403
        if request.method == 'POST' and request.path != '/api/clear_chat' and not request.is_json:
            return jsonify(status='error', error='Invia un oggetto JSON valido.'), 415

@app.after_request
def response_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    if not request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


SECRET_SETTING_KEYS = SECRET_KEYS


def public_settings() -> Dict[str, Any]:
    """Espone al browser solo preferenze non sensibili."""
    current = settings_manager.get_all()
    safe = {key: value for key, value in current.items() if key not in SECRET_SETTING_KEYS}
    safe['secrets_configured'] = {key: bool(current.get(key) or os.getenv(key.upper())) for key in SECRET_SETTING_KEYS}
    return safe


def runtime_status() -> Dict[str, Any]:
    current = settings_manager.get_all()
    model = str(current.get("model", "auto:free"))
    provider = "auto" if model == "auto:free" else (
        model.split(":", 1)[0] if ":" in model else "huggingface"
    )
    key_map = LLMEngine.provider_keys(current)
    configured_providers = [
        name
        for name in visible_providers(current)
        if key_map.get(name)
    ]
    return {
        "status": "online",
        "app_id": "aura-local",
        "app_version": "2.0.0",
        "project_id": hashlib.sha256(BASE_DIR.casefold().encode()).hexdigest()[:16],
        "assistant_name": current.get("assistant_name", "AURA"),
        "model": model,
        "provider": provider,
        "provider_configured": bool(configured_providers) if provider == "auto" else bool(key_map.get(provider)),
        "configured_providers": configured_providers,
        "memory_count": db_manager.get_message_count(),
        "voice_enabled": bool(current.get("voice_name")),
        "voice_effect": current.get("voice_effect", "none"),
        "tts_engine": current.get("tts_engine", "edge"),
        "local_voice_available": local_voice_available(),
        "qwen_voice_available": qwen_available(),
        "irodori_configured": bool(current.get('hf_api_key') or os.getenv('HF_API_KEY')),
        "voice_timbre_available": timbre_available(),
        "wake_enabled": bool(current.get("wake_enabled", True)),
        "wake_word": current.get("wake_word", "ehi aura"),
        "response_style": current.get("response_style", "balanced"),
        "ai_mode": current.get("ai_mode", "balanced"),
        "ai_health": [{**item,'models':visible_models(item['id'],current,item['models'])} for item in LLMEngine.health.snapshot(key_map) if item['id'] in visible_providers(current)],
    }

@app.context_processor
def aura_template_context():
    avatars = {
        'hiyori': {'id': 'hiyori', 'name': 'Hiyori', 'label': 'Hiyori Momose',
                   'path': '/static/models/hiyori/Hiyori.model3.json', 'portrait_height': 1.85,
                   'source': 'https://www.live2d.com/en/learn/sample/momose-hiyori/',
                   'expressions': {'felice': 'cozy-happy', 'triste': 'cozy-sad', 'allerta': 'cozy-alert', 'sorpresa': 'cozy-surprised'}},
        'haru': {'id': 'haru', 'name': 'Haru', 'label': 'Haru',
                 'path': '/static/models/haru/Haru.model3.json', 'portrait_height': 0,
                 'source': 'https://github.com/Live2D/CubismWebSamples/tree/4-r.7/Samples/Resources/Haru',
                 'expressions': {'felice': 'F01', 'triste': 'F04', 'allerta': 'F08', 'sorpresa': 'F06'}},
    }
    selected = settings_manager.get('avatar_model', 'hiyori')
    return {'dialect_meta': dialect_metadata(), 'avatar': avatars[selected],
            'provider_catalog': visible_providers(settings_manager.get_all()), 'settings_defaults': {k:v for k,v in DEFAULT_SETTINGS.items() if k not in SECRET_KEYS},
            'voice_timbre_available': timbre_available(),
            'local_voice_available': local_voice_available(), 'qwen_voice_available': qwen_available()}

from github_auth import GithubAccount
from settings_api import register_settings_api
app.config['AURA_VERSION'] = '2.0.0'
github_account = GithubAccount(app, settings_manager, DATA_DIR)
register_settings_api(app, settings_manager, DEFAULT_SETTINGS, AUDIO_CACHE_DIR)

@app.route("/")
def index():
    return render_template("index.html", settings=public_settings())

@app.route('/voice')
def voice_room():
    return render_template('voice.html', settings=public_settings())


@app.route('/api/voice/warm', methods=['POST'])
def voice_warm():
    if settings_manager.get_all().get('tts_engine') == 'qwen' and qwen_available():
        Thread(target=qwen_service.warm, daemon=True).start()
    return jsonify(state=qwen_service.state, accelerated=qwen_service.accelerated)


@app.route('/api/voice/status')
def voice_status():
    return jsonify(state=qwen_service.state, accelerated=qwen_service.accelerated)


@app.route("/settings")
def settings():
    return render_template("settings.html", settings=public_settings())

@app.route("/credits")
def credits():
    return render_template("credits.html", settings=public_settings())

@app.route("/api/status")
def status_api():
    return jsonify(runtime_status())

@app.route("/api/providers")
def providers_api():
    current = settings_manager.get_all()
    keys = LLMEngine.provider_keys(current)
    return jsonify({
        "status": "success",
        "mode": current.get("model", "auto:free"),
        "providers": [
            {
                "id": provider,
                "configured": bool(keys.get(provider)) if provider != "ollama" else None,
                "models": visible_models(provider,current,LLMEngine.health.catalog(provider,keys) or FREE_PROVIDER_MODELS.get(provider,([info['default']] if info['default'] else []))),
                "label": info['label'],
            }
            for provider, info in visible_providers(current).items()
        ],
    })

@app.route("/api/ai/check", methods=["POST"])
def ai_check_api():
    if not ai_check_lock.acquire(blocking=False):
        return jsonify(status='error', error='Una verifica è già in corso.'), 409
    try:
        return jsonify(status='success', providers=LLMEngine.diagnose(settings_manager.get_all()))
    finally:
        ai_check_lock.release()

@app.route('/api/dialects')
def dialects_api():
    return jsonify(status='success', profiles=dialect_metadata())

@app.route('/api/connect/openrouter', methods=['POST'])
def connect_openrouter_api():
    if 'openrouter' not in visible_providers(settings_manager.get_all()):
        return jsonify(status='error',error='Servizio escluso dalla selezione attiva.'),400
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('key', ''), str):
        return jsonify(status='error', error='Inserisci una chiave valida nel campo locale.'), 400
    new_key = data.get('key', '').strip()
    if new_key and (len(new_key) < 16 or len(new_key) > 512 or any(char.isspace() for char in new_key)):
        return jsonify(status='error', error='La chiave sembra incompleta. Copiala dalla pagina ufficiale di OpenRouter.'), 400
    if not ai_check_lock.acquire(blocking=False):
        return jsonify(status='error', error='Una verifica è già in corso.'), 409
    options = deadline = trace = None
    saved = False
    try:
        update = {'model': 'openrouter:openrouter/free', 'allow_fallback': False}
        if new_key:
            update['openrouter_api_key'] = new_key
        current = settings_manager.get_all()
        if not new_key and not LLMEngine.provider_keys(current).get('openrouter'):
            return jsonify(status='error', error='Apri la pagina ufficiale, crea una chiave personale e incollala qui.', key_saved=False), 400
        settings_manager.update(update)
        saved = True
        current = settings_manager.get_all()
        key = LLMEngine.provider_keys(current)['openrouter']
        options = generation_options.set({'max_tokens': 512, 'reasoning_effort': 'low'})
        deadline = provider_deadline.set(time.monotonic() + 30)
        trace = generation_info.set({})
        # Fixed, non-personal test. Never include the user's conversation.
        messages = [{'role': 'system', 'content': 'Rispondi in italiano con una sola breve frase, senza ragionamenti interni.'},
                    {'role': 'user', 'content': 'Saluta come AURA e conferma che il collegamento funziona.'}]
        raw = LLMEngine.call_openrouter(key, 'openrouter/free', messages)
        sample, _ = LLMEngine.parse_json_response(raw)
        if not sample:
            raise ValueError('Risposta vuota')
        LLMEngine.health.success('openrouter', LLMEngine.provider_keys(current), model='openrouter/free')
        return jsonify(status='success', message='AURA è collegata a OpenRouter Free.', sample=sample[:1000],
                       model=(generation_info.get() or {}).get('resolved_model', 'openrouter/free'), key_saved=True)
    except ValueError as error:
        if not saved:
            return jsonify(status='error', error='Non riesco a salvare la configurazione locale.', key_saved=False), 500
        return jsonify(status='error', error='Chiave salvata. Il servizio non ha completato la risposta di prova: puoi riprovare.', key_saved=True), 503
    except Exception as error:
        if not saved:
            return jsonify(status='error', error='Non riesco a salvare la configurazione locale.', key_saved=False), 500
        current = settings_manager.get_all()
        message, code = LLMEngine.health.failure('openrouter', LLMEngine.provider_keys(current), 'openrouter/free', error)
        hints = {401: 'Controlla di aver copiato la chiave completa.', 403: 'Controlla accesso, permessi e impostazioni dell’account OpenRouter.',
                 402: 'Controlla i limiti dell’account e della chiave sulla pagina ufficiale.', 429: 'La quota gratuita può essere esaurita: attendi e riprova.'}
        return jsonify(status='error', error=message + '. ' + hints.get(code, 'Il servizio potrebbe essere temporaneamente occupato.'),
                       key_saved=saved), code if code in (401, 402, 403, 429) else 503
    finally:
        if trace is not None: generation_info.reset(trace)
        if options is not None: generation_options.reset(options)
        if deadline is not None: provider_deadline.reset(deadline)
        ai_check_lock.release()

@app.route("/api/history")
def history_api():
    limit = request.args.get("limit", default=40, type=int)
    limit = max(1, min(limit or 40, 100))
    messages = get_active_chat_history(limit=limit) if settings_manager.get('history_enabled',True) else []
    return jsonify({
        "status": "success",
        "messages": messages,
        "count": db_manager.get_message_count(),
    })

@app.route("/api/save_settings", methods=["POST"])
def save_settings_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify(status='error', error='Dati non validi.'), 400
    try:
        if (data.get('github_require_login') is True or ('github_client_id' in data and settings_manager.get('github_require_login'))) and not github_account.authenticated():
            raise ValueError('Collega prima il tuo account GitHub in questo browser.')
        if settings_manager.get('github_require_login') and 'github_client_id' in data and data['github_client_id'] != settings_manager.get('github_client_id') and data.get('github_require_login',True):
            raise ValueError('Disattiva prima l’accesso obbligatorio per cambiare Client ID.')
        settings_manager.update(data)
    except ValueError as exc:
        return jsonify(status='error', error=str(exc)), 400
    except OSError:
        return jsonify(status='error', error='Impossibile salvare la configurazione.'), 500
    return jsonify(status='success', settings=public_settings())

@app.route("/api/clear_chat", methods=["POST"])
def clear_chat_api():
    try:
        if not chat_lock.acquire(blocking=False):
            return jsonify(status="error", error="Attendi la risposta prima di cancellare la memoria."), 409
        try:
            db_manager.clear_chat_history()
        finally:
            chat_lock.release()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route("/api/chat", methods=["POST"])
def chat_api():
    started_at = time.perf_counter()
    dati = request.get_json(silent=True)
    if not isinstance(dati, dict) or not isinstance(dati.get("message"), str):
        return jsonify(status="error", error="Il messaggio deve essere un testo."), 400
    user_message = dati["message"].strip()

    if not user_message:
        return jsonify({"status": "error", "error": "Il messaggio non può essere vuoto!"}), 400

    is_valid, msg_clean = LLMEngine.sanitize_input(user_message)
    if not is_valid:
        return jsonify({"status": "error", "error": msg_clean}), 400

    if not chat_lock.acquire(blocking=False):
        return jsonify(status='error', error='Una risposta è già in corso. Riprova tra poco.'), 409
    try:
        keep_history = settings_manager.get('history_enabled',True)
        history = get_active_chat_history(limit=200) if keep_history else []
        generation_info.set(None)
        bot_reply, emozione, provider, model_name = LLMEngine.generate_response(
            msg_clean, history, {**settings_manager.get_all(), 'voice_mode': dati.get('mode') == 'voice'})
        if provider == 'offline':
            return jsonify(status='error', error=bot_reply, provider=provider), 503
        # Persist a completed exchange in one transaction; failures don't poison memory.
        if keep_history:
            conn = db_manager._get_connection()
            try:
                with conn:
                    conn.executemany('INSERT INTO chat_history (role, content) VALUES (?, ?)',
                                     [('user', msg_clean), ('bot', bot_reply)])
            finally:
                conn.close()
    except Exception as exc:
        logger.error('Errore durante la conversazione: %s', type(exc).__name__)
        return jsonify(status='error', error='Non riesco a completare la richiesta. Riprova tra poco.'), 503
    finally:
        chat_lock.release()

    return jsonify({
        "status": "success",
        "response": bot_reply,
        "emozione": emozione,
        "provider": provider,
        "model": model_name,
        "latency_ms": round((time.perf_counter() - started_at) * 1000),
        "ai": generation_info.get() or {},
        "memory_count": db_manager.get_message_count(),
    })

@app.route('/api/tts/stream', methods=['POST'])
def tts_stream_api():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or not isinstance(data.get('text'),str) or not 0<len(data['text'].strip())<=600:
        return jsonify(error='Il segmento vocale deve contenere da 1 a 600 caratteri.'),400
    current=settings_manager.get_all()
    if current.get('tts_engine')!='qwen':
        return jsonify(error='La riproduzione progressiva richiede Qwen.'),409
    text=applica_pronuncia_perfetta(data['text'].strip(),current.get('dialect','standard'))
    style=current.get('qwen_voice_style','anime')
    language={'giapponese':'Japanese','coreano':'Korean'}.get(current.get('dialect'),'Italian')
    def audio_events():
        try:
            for audio in stream_qwen_speech(text,style,language):
                yield json.dumps({'event':'audio','audio':base64.b64encode(audio).decode('ascii')})+'\n'
            yield json.dumps({'event':'done'})+'\n'
        except NeuralVoiceError as error:
            yield json.dumps({'event':'error','error':str(error)})+'\n'
    return Response(stream_with_context(audio_events()),mimetype='application/x-ndjson',
                    headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


@app.route("/api/tts", methods=["POST"])
def tts_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('text'), str):
        return jsonify(status='error', error='Il testo deve essere una stringa.'), 400
    text = data['text'].strip()
    emotion = data.get('emotion', 'normale')
    if not isinstance(emotion, str) or len(emotion) > 24:
        return jsonify(status='error', error='Emozione non valida.'), 400
    emotion = emotion.lower()
    cur_settings = settings_manager.get_all()

    if not text:
        return "Nessun testo specificato", 400
    if len(text) > 2500:
        return "Testo troppo lungo per la sintesi vocale", 400

    try:
        dialect = cur_settings.get("dialect", "standard")
        text_phonetic = applica_pronuncia_perfetta(text, dialect)
        kawaii = cur_settings.get("use_kawaii_pitch", False)
        elite_model = cur_settings.get("elite_model")
        voice_name = cur_settings.get("voice_name", "it-IT-ElsaNeural")
        base_pitch_hz = cur_settings.get("voice_pitch_hz", 0)
        base_rate_percent = cur_settings.get("voice_rate_percent", 0)
        voice_character = cur_settings.get("voice_character", "soft")
        voice_effect = cur_settings.get("voice_effect", "none")
        tts_engine = cur_settings.get("tts_engine", "edge")
        local_style = cur_settings.get("local_voice_style", "hiyori")
        qwen_style = cur_settings.get('qwen_voice_style', 'anime')
        irodori_reading = cur_settings.get('irodori_reading', 'kana')
        mime = "audio/mp3" if tts_engine == "edge" else "audio/wav"
        extension = "mp3" if tts_engine == "edge" else "wav"

        # Include character and revision so older audio cannot hide a changed voice.
        cache_key = json.dumps([VOICE_REVISION, TIMBRE_REVISION, LOCAL_VOICE_REVISION, NEURAL_VOICE_REVISION, tts_engine, local_style, qwen_style, irodori_reading, voice_effect, text_phonetic, emotion, kawaii, elite_model,
                                dialect, voice_name, base_pitch_hz, base_rate_percent,
                                voice_character], ensure_ascii=False)
        cache_hash = hashlib.sha256(cache_key.encode('utf-8')).hexdigest()
        cache_file = os.path.join(AUDIO_CACHE_DIR, f"{cache_hash}.{extension}")

        if cur_settings.get('tts_cache_enabled',True) and os.path.exists(cache_file):
            return send_file(cache_file, mimetype=mime)

        if tts_engine == 'qwen':
            language = {'giapponese':'Japanese', 'coreano':'Korean'}.get(dialect, 'Italian')
            audio_data = generate_qwen_speech(text_phonetic, qwen_style, language)
        elif tts_engine == 'irodori':
            audio_data = generate_irodori_speech(text_phonetic,
                cur_settings.get('hf_api_key') or os.getenv('HF_API_KEY',''), irodori_reading, base_rate_percent)
        elif tts_engine == 'kokoro':
            audio_data = generate_local_speech(text_phonetic, local_style, base_rate_percent, emotion)
        else:
            audio_data = TTSEngine.generate_speech(text_phonetic, emotion, kawaii, elite_model,
                dialect, voice_name, base_pitch_hz, base_rate_percent, voice_character)

        if audio_data:
            if tts_engine == "edge":
                audio_data = apply_voice_timbre(audio_data, voice_effect)
            if cur_settings.get('tts_cache_enabled',True):
                cache_audio(cache_file, audio_data, cur_settings.get('tts_cache_mb',128)*1024*1024)
            return send_file(io.BytesIO(audio_data), mimetype=mime)
        else:
            return "Errore nella generazione audio", 500

    except NeuralVoiceError as error:
        return jsonify(status='error', error=str(error)), 503
    except Exception as e:
        logger.error("Errore endpoint TTS: %s", type(e).__name__)
        return jsonify(status="error", error="Sintesi vocale temporaneamente non disponibile."), 503

if __name__ == "__main__":
    from waitress import serve
    if settings_manager.get('tts_engine') == 'qwen' and qwen_available():
        Thread(target=qwen_service.warm, daemon=True).start()
    serve(app, host='127.0.0.1', port=int(os.getenv('JARVIS_PORT', '5001')), threads=8)
