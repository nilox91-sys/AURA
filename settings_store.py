"""Validated, atomic local configuration. Empty credentials preserve saved keys."""
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from preferences import ENUMS, TEXT_LIMITS, MULTILINE, validate_endpoint

SECRET_KEYS = {'hf_api_key', 'groq_api_key', 'gemini_api_key', 'openrouter_api_key', 'openai_api_key', 'anthropic_api_key', 'mistral_api_key', 'deepseek_api_key', 'lmstudio_api_key', 'compatible_api_key'}


class SettingsManager:
    def __init__(self, filepath, defaults):
        self.filepath = Path(filepath)
        self.defaults = dict(defaults)
        self.settings = dict(defaults)
        self.lock = RLock()
        if self.filepath.exists():
            with self.filepath.open(encoding='utf-8-sig') as stream:
                saved = json.load(stream)
            if not isinstance(saved, dict):
                raise ValueError('settings.json deve contenere un oggetto JSON.')
            for key, value in saved.items():
                if key in defaults and key != 'schema_version':
                    try:
                        self.settings[key] = self.validate(key, value)
                    except ValueError:
                        logging.getLogger('Jarvis.Settings').warning('Impostazione non valida: %s; uso il valore predefinito.', key)

    def validate(self, key, value):
        default = self.defaults[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f'{key}: è richiesto un valore sì/no.')
        elif isinstance(default, int):
            bounds = {'voice_pitch_hz': (-35, 20), 'voice_rate_percent': (-20, 20),
                      'context_turns': (1, 30), 'context_chars': (4000, 64000),
                      'max_response_tokens': (512, 8192), 'tts_cache_mb': (16, 512), 'ai_timeout_seconds': (15, 180)}
            low, high = bounds.get(key, (0, 100))
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'{key}: inserisci un intero tra {low} e {high}.')
        else:
            max_length = 512 if key in SECRET_KEYS else TEXT_LIMITS.get(key, 160)
            if not isinstance(value, str) or len(value) > max_length:
                raise ValueError(f'{key}: testo non valido o troppo lungo.')
            value = value.strip()
            if any(ord(char) < 32 and not (key in MULTILINE and char in '\n\r\t') for char in value):
                raise ValueError(f'{key}: caratteri non validi.')
            if key not in SECRET_KEYS and key not in TEXT_LIMITS and not value:
                raise ValueError(f'{key}: il campo non può essere vuoto.')
            if key in {'assistant_name', 'user_name', 'wake_word'} and len(value) > 32:
                raise ValueError(f'{key}: massimo 32 caratteri.')
            if key == 'dialect_intensity' and value not in {'gentle', 'balanced', 'authentic'}:
                raise ValueError('Intensità del dialetto non valida.')
            if key == 'pronunciation_mode' and value not in {'natural', 'assisted'}:
                raise ValueError('Modalità di pronuncia non valida.')
            if key == 'ai_mode' and value not in {'fast', 'balanced', 'reasoning'}:
                raise ValueError('Profilo AI non valido.')
            if key == 'response_style' and value not in {'concise', 'balanced', 'detailed'}:
                raise ValueError('Stile di risposta non valido.')
            if key == 'personality_profile' and value not in {'cozy_nerd', 'neutral', 'creative', 'mentor'}:
                raise ValueError('Personalità non valida.')
            if key == 'nerd_intensity' and value not in {'gentle', 'balanced', 'enthusiastic'}:
                raise ValueError('Intensità nerd non valida.')
            if key == 'voice_character' and value not in {'soft', 'cozy', 'natural'}:
                raise ValueError('Carattere della voce non valido.')
            if key == 'voice_effect' and value not in {'none', 'young', 'anime'}:
                raise ValueError('Resa del timbro non valida.')
            if key == 'tts_engine' and value not in {'edge', 'kokoro', 'irodori', 'qwen'}:
                raise ValueError('Motore vocale non valido.')
            if key == 'qwen_voice_style' and value not in {'anime', 'original'}:
                raise ValueError('Profilo Qwen non valido.')
            if key == 'irodori_reading' and value not in {'kana', 'original'}:
                raise ValueError('Lettura Irodori non valida.')
            if key == 'local_voice_style' and value not in {'hiyori', 'hiyori_soft', 'sara'}:
                raise ValueError('Voce locale non valida.')
            if key == 'avatar_model' and value not in {'hiyori', 'haru'}:
                raise ValueError('Personaggio non valido.')
            if key == 'voice_name' and not re.fullmatch(r'[a-z]{2}-[A-Z]{2}-[A-Za-z]+Neural', value):
                raise ValueError('Nome della voce non valido.')
            if key == 'model' and not re.fullmatch(r'[\w./:+-]+', value):
                raise ValueError('Identificativo modello non valido.')
            if key in ENUMS and value not in ENUMS[key]:
                raise ValueError(f'{key}: scelta non valida.')
            if key == 'github_client_id' and value and not re.fullmatch(r'[A-Za-z0-9_.-]{4,100}', value):
                raise ValueError('Client ID GitHub non valido.')
            if key in {'ollama_host','lmstudio_host','compatible_base_url'}:
                value = validate_endpoint(value)
        return value

    def update(self, new_data, clear_keys=()):
        with self.lock:
            candidate = dict(self.settings)
            for key in clear_keys:
                if key not in SECRET_KEYS:raise ValueError('Credenziale non riconosciuta.')
                candidate[key]=''
            for key, value in new_data.items():
                if key not in self.defaults or key == 'schema_version':
                    raise ValueError(f'Impostazione non riconosciuta: {key}.')
                validated = self.validate(key, value)
                if key in SECRET_KEYS and not validated:
                    continue
                candidate[key] = validated
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.filepath.parent, delete=False) as stream:
                    temporary = stream.name
                    json.dump(candidate, stream, ensure_ascii=False, indent=4)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.filepath)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            self.settings = candidate

    def get_all(self):
        with self.lock:
            return dict(self.settings)

    def get(self, key, default=None):
        with self.lock:
            return self.settings.get(key, default)
