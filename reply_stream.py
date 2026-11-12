"""Incremental extraction of AURA's JSON envelope without exposing JSON or reasoning."""
import json
import re


def string_prefix(source, start):
    """Decode complete escapes only, including split UTF-16 surrogate pairs."""
    result, index = [], start + 1
    while index < len(source):
        char = source[index]
        if char == '"':
            return ''.join(result), index + 1, True
        if char != '\\':
            if ord(char) < 32:
                raise ValueError('Stringa JSON non valida')
            result.append(char)
            index += 1
            continue
        if index + 1 >= len(source):
            break
        escape = source[index + 1]
        if escape != 'u':
            mapping = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
            if escape not in mapping:
                raise ValueError('Escape JSON non valido')
            result.append(mapping[escape])
            index += 2
            continue
        if index + 6 > len(source):
            break
        code = int(source[index + 2:index + 6], 16)
        end = index + 6
        if 0xD800 <= code <= 0xDBFF:
            if end + 6 > len(source):
                break
            if source[end:end + 2] != '\\u':
                raise ValueError('Unicode JSON non valido')
            low = int(source[end + 2:end + 6], 16)
            if not 0xDC00 <= low <= 0xDFFF:
                raise ValueError('Unicode JSON non valido')
            code = 0x10000 + ((code - 0xD800) << 10) + low - 0xDC00
            end += 6
        elif 0xDC00 <= code <= 0xDFFF:
            raise ValueError('Unicode JSON non valido')
        result.append(chr(code))
        index = end
    return ''.join(result), index, False


class ReplyDecoder:
    def __init__(self):
        self.raw = ''
        self.text = ''
        self.emotion = 'normale'

    def feed(self, delta):
        self.raw += delta
        if len(self.raw) > 128000:
            raise ValueError('Risposta troppo lunga')
        source = self.raw.lstrip()
        # A fence may itself be split across any number of transport chunks.
        if source.startswith('`'):
            fence = re.match(r'^```(?:json)?\s*\{', source)
            if fence:
                source = source[fence.end() - 1:]
            elif any(prefix.startswith(source) for prefix in ('```json', '```')) or re.fullmatch(r'```(?:json)?\s*', source):
                return ''
            else:
                return self._new_text(source)
        if not source or source == '{':
            return ''
        if not source.startswith('{'):
            return self._new_text(source)
        decoder = json.JSONDecoder()
        index = 1
        while index < len(source):
            while index < len(source) and source[index] in ' \t\r\n,':
                index += 1
            try:
                key, end = decoder.raw_decode(source, index)
            except ValueError:
                break
            if not isinstance(key, str):
                break
            index = end
            while index < len(source) and source[index].isspace():
                index += 1
            if index >= len(source) or source[index] != ':':
                break
            index += 1
            while index < len(source) and source[index].isspace():
                index += 1
            if index >= len(source):
                break
            if key == 'testo' and source[index] == '"':
                text, _, _ = string_prefix(source, index)
                return self._new_text(text.lstrip())
            try:
                value, index = decoder.raw_decode(source, index)
            except ValueError:
                break
            if key == 'emozione' and value in ('normale', 'felice', 'triste', 'allerta', 'sorpresa'):
                self.emotion = value
        return ''

    def _new_text(self, text):
        if not text.startswith(self.text):
            raise ValueError('La risposta ha cambiato il testo già ricevuto')
        delta = text[len(self.text):]
        self.text = text
        return delta
