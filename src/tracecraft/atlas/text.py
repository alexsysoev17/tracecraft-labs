"""Morphological lexical normalization; no gold, IDs or answer facts in this layer."""
import re
import threading
from functools import lru_cache

import snowballstemmer

_LOCK = threading.Lock()
_STEMMERS = {lang: snowballstemmer.stemmer(lang) for lang in ('english','russian')}
STOP = set('what is are was were the a an of for in and to can how which brand use used should please tell me about '
           'does do did may must be it its this that with as by at on or have has from would could '
           'какой какая какие какое как и в на для ли что можно нужно бренда бренд у мне '
           'это есть был была были будет ли или по об о во со из за до при '
           'much other elements stay сколько оставить '
           'please tell me luma field veyra works v1 v2'.split())
# A small declared design-domain glossary supplements morphology. These are
# language aliases, not benchmark queries or brand facts; absent attributes
# (for example CMYK conversions) are deliberately not inferred.
ALIASES = {'around':'clearspace','вокруг':'clearspace','distance':'clearspace',
           'расстояние':'clearspace','отступ':'clearspace','отступы':'clearspace','far':'clearspace'}

@lru_cache(maxsize=8192)
def stem(word):
    language = 'russian' if re.search('[а-яё]',word) else 'english'
    with _LOCK:
        return _STEMMERS[language].stemWord(word)

def tokens(text):
    return [stem(ALIASES.get(t,t)) for t in re.findall(r'[\w]+',text.casefold()) if len(t)>1 and t not in STOP]
