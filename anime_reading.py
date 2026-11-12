"""Lossy Italian-to-kana reading aid for Japanese-only Irodori; never a translation."""
import re
import unicodedata

_VOWELS = {'a':'ア','e':'エ','i':'イ','o':'オ','u':'ウ'}
_ROWS = {
    'k':['カ','ケ','キ','コ','ク'], 'g':['ガ','ゲ','ギ','ゴ','グ'],
    's':['サ','セ','シ','ソ','ス'], 'z':['ザ','ゼ','ジ','ゾ','ズ'],
    't':['タ','テ','ティ','ト','トゥ'], 'd':['ダ','デ','ディ','ド','ドゥ'],
    'n':['ナ','ネ','ニ','ノ','ヌ'], 'h':['ハ','ヘ','ヒ','ホ','フ'],
    'b':['バ','ベ','ビ','ボ','ブ'], 'p':['パ','ペ','ピ','ポ','プ'],
    'm':['マ','メ','ミ','モ','ム'], 'r':['ラ','レ','リ','ロ','ル'],
    'l':['ラ','レ','リ','ロ','ル'], 'f':['ファ','フェ','フィ','フォ','フ'],
    'v':['ヴァ','ヴェ','ヴィ','ヴォ','ヴ'],
    'ch':['チャ','チェ','チ','チョ','チュ'], 'j':['ジャ','ジェ','ジ','ジョ','ジュ'],
    'sh':['シャ','シェ','シ','ショ','シュ'], 'ny':['ニャ','ニェ','ニ','ニョ','ニュ'],
    'ly':['リャ','リェ','リ','リョ','リュ'],
}
_FINAL = {'n':'ン','m':'ン','r':'ル','l':'ル','t':'ト','d':'ド','k':'ク','g':'グ',
          's':'ス','z':'ズ','f':'フ','v':'ヴ','b':'ブ','p':'プ','ch':'チ','j':'ジ','sh':'シュ'}
_WORDS = {'aura':'アウラ','ehi':'エイ','hai':'アイ','curiosa':'クリオーザ',
          'insieme':'インシエーメ','costruiamo':'コストゥルイアーモ'}


def _word(word):
    word = ''.join(c for c in unicodedata.normalize('NFD',word.casefold()) if not unicodedata.combining(c))
    if word in _WORDS:
        return _WORDS[word]
    phones, i = [], 0
    while i < len(word):
        rest = word[i:]
        matched = False
        for letters, sound in [('gli','ly'),('gn','ny'),('sci','sh'),('sce','sh'),('chi','k'),('che','k'),('ghi','g'),('ghe','g'),('cia','ch'),('cio','ch'),('ciu','ch'),('gia','j'),('gio','j'),('giu','j')]:
            if rest.startswith(letters):
                # Keep the final vowel when it is pronounced (sce/che/ghe/chi/ghi).
                phones.append(sound)
                if letters in {'sce','che','ghe','chi','ghi','cia','cio','ciu','gia','gio','giu'} or (letters == 'gli' and (i+3 == len(word) or word[i+3] not in 'aeou')):
                    phones.append(letters[-1])
                i += len(letters); matched = True; break
        if matched:
            continue
        c = word[i]
        if c == 'h':
            i += 1; continue
        if i+1 < len(word) and c == word[i+1] and c not in 'aeiou':
            phones.append('ッ'); i += 1; continue
        if c == 'c': c = 'ch' if i+1 < len(word) and word[i+1] in 'ei' else 'k'
        elif c == 'g' and i+1 < len(word) and word[i+1] in 'ei': c = 'j'
        elif c == 'q': c = 'k'
        elif c == 's' and 0 < i < len(word)-1 and word[i-1] in 'aeiou' and word[i+1] in 'aeiou': c = 'z'
        phones.append(c); i += 1
    result, i = [], 0
    while i < len(phones):
        c = phones[i]
        if c in _VOWELS:
            result.append(_VOWELS[c]); i += 1
        elif c in _ROWS and i+1 < len(phones) and phones[i+1] in _VOWELS:
            result.append(_ROWS[c]['aeiou'.index(phones[i+1])]); i += 2
        else:
            result.append(_FINAL.get(c,c)); i += 1
    return ''.join(result)


def anime_reading(text):
    """Preserve punctuation, digits and existing Japanese; rewrite only Latin words."""
    return re.sub(r'[A-Za-zÀ-ÖØ-öø-ÿ]+',lambda m:_word(m.group()),text)
