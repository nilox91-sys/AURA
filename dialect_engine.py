"""Dialect register and speech pronunciation are separate, explicit operations."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PROFILES = json.loads((ROOT / 'dialect_profiles.json').read_text(encoding='utf-8'))
INTENSITIES = ('gentle', 'balanced', 'authentic')


def build_dialect_prompt(dialect, intensity='balanced', legacy=None):
    intensity = intensity if intensity in INTENSITIES else 'balanced'
    if dialect == 'standard':
        return 'Usa italiano naturale, chiaro e cordiale. Rispetta la lingua esplicitamente richiesta nel messaggio corrente.'
    profile = PROFILES.get(dialect)
    if profile:
        result = '\n'.join(['Registro linguistico: ' + profile['label'], profile['scope'],
                          *profile['guidance'], 'Intensità: ' + profile['intensities'][intensity],
                          'Esempio orientativo di registro, da non ripetere come formula: ' + profile['previews'][intensity]])
        if dialect == 'napoletano' and intensity == 'authentic':
            result += '\nLa risposta va scritta IN NAPOLETANO, anche per spiegazioni tecniche: non basta un saluto dialettale seguito da italiano. Esempio di stile, non di contenuto: domanda «Come iniziamo?»; risposta JSON {"emozione":"normale","testo":"Partimmo dâ cosa cchiù semplice. Dimme che vuò fa’ e vedimmo ’nzieme ’o primmo passo."}'
        return result
    prompt = (legacy or {}).get(dialect, '')
    return (str(prompt) + '\nNon alterare codice, numeri o nomi propri. La lingua richiesta esplicitamente dall’utente ha priorità.') if prompt else ''


def dialect_metadata():
    profile = PROFILES['napoletano']
    return {'napoletano': {key: profile[key] for key in ('label', 'previews', 'note', 'sources')}}


def prepare_tts_text(text, dialect='standard', mode='natural', phonetics=None):
    # Natural neural speech is the default: it never rewrites the user's prose.
    if not text or mode != 'assisted':
        return text
    data = phonetics or {}
    substitutions = dict(data.get('global', {}))
    substitutions.update(data.get('dialects', {}).get(dialect, {}))
    substitutions = {key.casefold(): value for key, value in substitutions.items()
                     if isinstance(key, str) and key and isinstance(value, str)}
    if not substitutions:
        return text
    alternatives = sorted(substitutions, key=len, reverse=True)
    expression = re.compile(r'(?<!\w)(' + '|'.join(re.escape(key) for key in alternatives) + r')(?!\w)', re.IGNORECASE)
    protected = re.compile(r'(```[\s\S]*?```|`[^`]*`|https?://[^\s]+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})')
    parts = protected.split(text)
    for index in range(0, len(parts), 2):
        parts[index] = expression.sub(lambda match: substitutions[match.group(0).casefold()], parts[index])
    return ''.join(parts)
