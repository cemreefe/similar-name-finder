from dataclasses import dataclass
from enum import Enum
from typing import assert_never
from flask import Flask, Response, render_template, request, redirect, url_for
try:
    from api.translations import get_translations, get_arabic_page_translations, get_korean_page_translations, LANGUAGES, RTL_LANGUAGES
except ImportError:
    from translations import get_translations, get_arabic_page_translations, get_korean_page_translations, LANGUAGES, RTL_LANGUAGES
import sqlite3
from metaphone import doublemetaphone
import helpers.metaphone_helper as mhelp
from eng_to_ipa import ipa_list
from jellyfish import jaro_winkler_similarity, damerau_levenshtein_distance
import os
from urllib.parse import quote, unquote, urlencode
from xml.sax.saxutils import escape

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_URL = 'https://namefinder.dutl.uk'
_DB_PATH = os.path.join(os.path.dirname(_THIS_DIR), 'names_database.db')
_ARAB_DB_PATH = os.path.join(os.path.dirname(_THIS_DIR), 'arabnames_database.db')
_KOREAN_DB_PATH = os.path.join(os.path.dirname(_THIS_DIR), 'korean_database.db')
import re
import unicodedata


class InputType(Enum):
    ENGLISH = 'english'
    TURKISH = 'turkish'
    CHINESE = 'chinese'
    KOREAN = 'korean'
    FRENCH = 'french'
    FILIPINO = 'filipino'
    JAPANESE = 'japanese'
    SPANISH = 'spanish'
    PORTUGUESE = 'portuguese'
    GERMAN = 'german'
    ITALIAN = 'italian'
    RUSSIAN = 'russian'
    ARABIC = 'arabic'
    HINDI = 'hindi'
    AUTO = 'auto'
    IPA = 'ipa'
    MP = 'mp'


class DistanceDimension(Enum):
    IPA = 'ipa'
    SEMI = 'semi'
    MP = 'mp'
    SOUND = 'sound'
    SPELLING = 'spelling'


@dataclass
class NameRepr:
    name: str
    ipa: str | None = None
    semi: str | None = None
    mp: str | None = None


def _distance(x, y):
    return 1 - jaro_winkler_similarity(x, y)

def _mp_distance(input_mp: str, db_mp: str) -> float:
    """
    MP distance = normalized Damerau–Levenshtein + edge penalty.

    DL treats transpositions as single operations (cost 1) and properly
    penalizes very short DB codes for missing characters, unlike Jaro–Winkler
    which over-rewards prefix matches on 1–4 char MP strings.  The edge
    penalty adds sequential-order information on top: wrong bigrams that
    appear in the DB code but not in the input code are penalised, with
    swapped (reversed) edges receiving half the penalty.
    """
    max_len = max(len(input_mp), len(db_mp), 1)
    base = damerau_levenshtein_distance(input_mp, db_mp) / max_len

    def edges(s: str) -> list[str]:
        return [s[i : i + 2] for i in range(len(s) - 1)]

    input_edges = set(edges(input_mp))
    db_edges = edges(db_mp)
    if not db_edges:
        return base

    wrong = 0.0
    for e in db_edges:
        if e in input_edges:
            continue
        wrong += 0.5 if e[::-1] in input_edges else 1.0
    return base + (wrong * 0.03)


def _chinese_to_pinyin(text: str) -> str | None:
    try:
        from pypinyin import pinyin, Style
    except ImportError:
        return None
    try:
        syls = pinyin(text, style=Style.NORMAL, neutral_tone_with_five=True)
        return ' '.join(s[0] for s in syls).lower()
    except Exception:
        return None


def _hangul_to_phonetic_romanization(text: str) -> str | None:
    """Hangul to pronunciation-aware romanization for Metaphone (avoids ghost letters like 'r' in Park)."""
    if not any('\uac00' <= c <= '\ud7af' for c in text):
        return None
    phon = mhelp.hangul_to_phonetic_romanization(text)
    if phon:
        return phon
    try:
        from korean_romanizer import Romanizer
        return Romanizer(text).romanize().lower()
    except Exception:
        return None


def _japanese_to_romaji(text: str) -> str | None:
    if not any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' for c in text):
        return None
    try:
        import pykakasi
        kks = pykakasi.kakasi()
        result = kks.convert(text)
        return ''.join(r.get('hepburn', r.get('orig', '')) for r in result).lower()
    except Exception:
        return None


def _encode(name, input_type: InputType) -> NameRepr:
    def romanized_normalized(s: str) -> str:
        return (s or '').capitalize()

    def romanized_ipa(s: str) -> str | None:
        normalized = romanized_normalized(s)
        ipa_result = ipa_list(normalized)
        return ipa_result[0][0] if ipa_result else None

    def romanized_mp(s: str) -> str | None:
        normalized = romanized_normalized(s)
        raw = doublemetaphone(normalized)[0]
        return raw.upper() if raw else None

    def chinese_ipa(s: str) -> str | None:
        try:
            from pinyin_to_ipa import pinyin_to_ipa
        except ImportError:
            return None

        pinyin_str = (s or '').lower().strip()
        if not pinyin_str:
            return None

        if any('\u4e00' <= c <= '\u9fff' for c in s):
            pinyin_str = _chinese_to_pinyin(s) or ''
        if not pinyin_str:
            return None

        ipa_parts: list[str] = []
        for part in pinyin_str.split():
            try:
                result = pinyin_to_ipa(part)
                if not result:
                    return None
                first = list(result)[0]
                ipa_parts.append(''.join(str(x) for x in first))
            except Exception:
                return None
        return ''.join(ipa_parts) if ipa_parts else None

    def korean_romanized(s: str) -> str | None:
        return _hangul_to_phonetic_romanization(s)

    def japanese_romanized(s: str) -> str | None:
        return _japanese_to_romaji(s)

    def arabic_ipa(s: str) -> str | None:
        if any('\u0600' <= c <= '\u06ff' for c in s):
            return mhelp.arabic_to_ipa(s) or None
        return romanized_ipa(s)

    def hindi_ipa(s: str) -> str | None:
        if any('\u0900' <= c <= '\u097f' for c in s):
            return mhelp.hindi_to_ipa(s) or None
        return romanized_ipa(s)

    def _transform(s: str, it: InputType, rep: DistanceDimension, cached_ipa: str | None = None) -> str | None:
        match (it, rep):
            case (InputType.MP, DistanceDimension.MP):
                return (s or '').upper() or None
            case (InputType.IPA, DistanceDimension.IPA):
                return (s or '').strip() or None
            case (InputType.IPA, DistanceDimension.SEMI):
                return mhelp.ipa_to_semiphonetic((s or '').strip() or None)
            case (_, DistanceDimension.SEMI):
                ipa = cached_ipa if cached_ipa is not None else _transform(s, it, DistanceDimension.IPA)
                return mhelp.ipa_to_semiphonetic(ipa)
            case (InputType.TURKISH, DistanceDimension.IPA):
                return mhelp.turkish_to_ipa(s)
            case (InputType.FRENCH, DistanceDimension.IPA):
                return mhelp.french_to_ipa(s)
            case (InputType.SPANISH, DistanceDimension.IPA):
                return mhelp.spanish_to_ipa(s)
            case (InputType.PORTUGUESE, DistanceDimension.IPA):
                return mhelp.portuguese_to_ipa(s)
            case (InputType.GERMAN, DistanceDimension.IPA):
                return mhelp.german_to_ipa(s)
            case (InputType.ITALIAN, DistanceDimension.IPA):
                return mhelp.italian_to_ipa(s)
            case (InputType.RUSSIAN, DistanceDimension.IPA):
                return mhelp.russian_to_ipa(s)
            case (InputType.ARABIC, DistanceDimension.IPA):
                return arabic_ipa(s)
            case (InputType.HINDI, DistanceDimension.IPA):
                return hindi_ipa(s)
            case (InputType.CHINESE, DistanceDimension.IPA):
                return chinese_ipa(s) or romanized_ipa(s)
            case (InputType.KOREAN, DistanceDimension.IPA):
                romanized = korean_romanized(s)
                return romanized_ipa(romanized) if romanized else romanized_ipa(s)
            case (InputType.JAPANESE, DistanceDimension.IPA):
                romanized = japanese_romanized(s)
                return romanized_ipa(romanized) if romanized else romanized_ipa(s)
            case (InputType.ENGLISH | InputType.FILIPINO, DistanceDimension.IPA):
                return romanized_ipa(s)

            case (InputType.SPANISH, DistanceDimension.MP):
                return romanized_mp(mhelp.strip_accents(s))
            case (InputType.ARABIC, DistanceDimension.MP) if not any('\u0600' <= c <= '\u06ff' for c in s):
                return romanized_mp(s)
            case (InputType.HINDI, DistanceDimension.MP) if not any('\u0900' <= c <= '\u097f' for c in s):
                return romanized_mp(s)
            case (
                InputType.TURKISH | InputType.FRENCH | InputType.PORTUGUESE
                | InputType.GERMAN | InputType.ITALIAN | InputType.RUSSIAN | InputType.ARABIC | InputType.HINDI,
                DistanceDimension.MP,
            ):
                ipa = cached_ipa if cached_ipa is not None else _transform(s, it, DistanceDimension.IPA)
                return mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P') if ipa else None
            case (InputType.CHINESE, DistanceDimension.MP):
                ipa = cached_ipa if cached_ipa is not None else _transform(s, it, DistanceDimension.IPA)
                return mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P') if ipa else romanized_mp(s)
            case (InputType.ENGLISH | InputType.FILIPINO, DistanceDimension.MP):
                return romanized_mp(s)
            case (InputType.KOREAN, DistanceDimension.MP):
                if any('\uac00' <= c <= '\ud7af' for c in s):
                    mp = mhelp.hangul_to_metaphone(s)
                    if mp:
                        return mp.upper()
                romanized = korean_romanized(s)
                if romanized:
                    return romanized_mp(mhelp.normalize_korean_for_metaphone(romanized))
                return romanized_mp(mhelp.normalize_korean_for_metaphone(s))
            case (InputType.JAPANESE, DistanceDimension.MP):
                romanized = japanese_romanized(s)
                return romanized_mp(romanized) if romanized else romanized_mp(s)
            case (_, DistanceDimension.MP):
                return None
            case (_, _):
                return None

    ipa = _transform(name, input_type, DistanceDimension.IPA)
    semi = _transform(name, input_type, DistanceDimension.SEMI, cached_ipa=ipa)
    mp = _transform(name, input_type, DistanceDimension.MP, cached_ipa=ipa)
    return NameRepr(name, ipa=ipa, semi=semi, mp=mp)


_CONSONANTS = set('BCDFGHJKLMNPQRSTVWXYZ0')

def _first_letter_penalty(input_mp: str, name_mp: str, weight: float = 0.15) -> float:
    if not input_mp or not name_mp:
        return 0.0
    first_in, first_db = input_mp[0].upper(), name_mp[0].upper()
    if first_in not in _CONSONANTS:
        return 0.0
    return 0.0 if first_in == first_db else weight


def _strip_diacritics(text):
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def _spelling_score(input_name, name):
    a = re.sub(r'(.)\1+', r'\1', _strip_diacritics(input_name.lower()))
    b = re.sub(r'(.)\1+', r'\1', _strip_diacritics(name.lower()))
    return _distance(a, b)


_DEFAULT_REPR_ORDER = (DistanceDimension.MP, DistanceDimension.SEMI, DistanceDimension.SPELLING)
_SEMI_CONSONANTS = set('BCDFGHJKLMNPQRSTVWXYZ')


def _first_consonant(s: str | None, consonants: set[str]) -> str | None:
    if not s:
        return None
    for c in s.upper():
        if c in consonants:
            return c
    return None


def _first_consonant_penalty(a: str | None, b: str | None, consonants: set[str], weight: float) -> float:
    fa = _first_consonant(a, consonants)
    fb = _first_consonant(b, consonants)
    if not fa or not fb:
        return 0.0
    return 0.0 if fa == fb else weight


def _repr_order() -> list[DistanceDimension]:
    raw = os.environ.get('NAMEF_REPR_ORDER')
    if not raw:
        return list(_DEFAULT_REPR_ORDER)

    token_to_dim = {
        'mp': DistanceDimension.MP,
        'semi': DistanceDimension.SEMI,
        'spelling': DistanceDimension.SPELLING,
    }
    parts = [p.strip().lower() for p in raw.split(',') if p.strip()]
    filtered = [token_to_dim[p] for p in parts if p in token_to_dim]
    return filtered or list(_DEFAULT_REPR_ORDER)


def _ipa_alternatives(ipa_alts: str | None) -> list[str]:
    if not ipa_alts:
        return []
    return [p.strip() for p in ipa_alts.split(',') if p.strip()]


def _semi_best_match(input_semi: str | None, ipa: str | None, ipa_alts: str | None) -> tuple[float, str] | None:
    if not input_semi:
        return None
    variants = []
    if ipa:
        variants.append(mhelp.ipa_to_semiphonetic(ipa))
    for alt in _ipa_alternatives(ipa_alts):
        variants.append(mhelp.ipa_to_semiphonetic(alt))
    variants = [v for v in variants if v]
    if not variants:
        return None
    best: tuple[float, str] | None = None
    for v in variants:
        d = mhelp.semiphonetic_distance(input_semi, v)
        if d is None:
            continue
        if best is None or d < best[0]:
            best = (d, v)
    return best


def _semi_distance(input_semi: str | None, ipa: str | None, ipa_alts: str | None) -> float | None:
    best = _semi_best_match(input_semi, ipa, ipa_alts)
    return best[0] if best else None


def _score_with_order(
    encoded: NameRepr,
    primary: DistanceDimension,
    order: list[DistanceDimension],
    name: str,
    name_mp: str | None,
    name_ipa: str | None,
    name_ipa_alts: str | None,
) -> float:
    score = 0.0
    semi_best: str | None = None

    for idx, repr_name in enumerate(order):
        weight = 1 if idx == 0 else 100 ** idx
        part = None

        match repr_name:
            case DistanceDimension.MP:
                if encoded.mp and name_mp:
                    part = _mp_distance(encoded.mp, name_mp)
                    score += _first_letter_penalty(encoded.mp, name_mp) / weight
            case DistanceDimension.SEMI:
                best = _semi_best_match(encoded.semi, name_ipa, name_ipa_alts)
                if best:
                    part, semi_best = best
                    score += _first_consonant_penalty(encoded.semi, semi_best, _SEMI_CONSONANTS, weight=0.25) / weight
            case DistanceDimension.SPELLING:
                part = _spelling_score(encoded.name, name)
            case _:
                part = None

        if part is not None:
            score += part / weight

    return score


app = Flask(__name__)


@app.context_processor
def _inject_lang_default_input_type():
    lang = request.args.get('lang', 'en')
    return {'lang_default_input_type': DEFAULT_INPUT_TYPE, 'lang_input_hint': LANG_TO_INPUT_TYPE.get(lang, 'english')}


@app.context_processor
def _inject_seo_context():
    lang = _get_lang()
    product = _current_product()
    return {
        'ui_flags': UI_FLAGS,
        'rtl_languages': RTL_LANGUAGES,
        'input_type_options': (AUTO_INPUT_OPTION,) + INPUT_TYPE_OPTIONS,
        'canonical_url': _BASE_URL + _canonical_path(),
        'product_home_url': _BASE_URL + PRODUCT_PATHS[product],
        'robots_noindex': _is_filtered_request(),
        'popular_links': [
            (name, _search_path(product, name, input_type, lang))
            for name, input_type in POPULAR_SEARCHES[product]
        ],
    }


@app.after_request
def _cache_headers(response):
    if request.method == 'GET' and response.status_code in (200, 301, 302, 308) and 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'public, max-age=0, s-maxage=86400, stale-while-revalidate=604800'
    return response


def _score(encoded: NameRepr, dim: DistanceDimension, name: str, name_mp: str | None, name_ipa: str | None, name_ipa_alts: str | None) -> float:
    if dim is DistanceDimension.SPELLING:
        return _spelling_score(encoded.name, name)

    primary = DistanceDimension.MP if dim is DistanceDimension.MP else DistanceDimension.SEMI
    order = [primary] + [x for x in _repr_order() if x is not primary]
    return _score_with_order(encoded, primary, order, name, name_mp, name_ipa, name_ipa_alts)


_AUTO_LATIN_TYPES = ('english', 'turkish', 'spanish', 'portuguese', 'german', 'italian', 'french', 'filipino', 'russian')

# First matching group wins; order puts the most language-specific letters first.
_DIACRITIC_HINTS = (
    ('ışğİŞĞ', ('turkish',)),
    ('ñ', ('spanish',)),
    ('ãõ', ('portuguese',)),
    ('ß', ('german',)),
    ('èêëœîû', ('french',)),
    ('ìò', ('italian',)),
    ('äöü', ('german', 'turkish')),
    ('çâ', ('turkish', 'french', 'portuguese')),
    ('é', ('spanish', 'french', 'portuguese')),
    ('áíóú', ('spanish', 'portuguese')),
)


def resolve_auto_input_types(name: str, hint: str | None = None) -> list[str]:
    script = _detect_input_script(name)
    if script:
        return [script]
    for chars, types in _DIACRITIC_HINTS:
        if any(c in name for c in chars):
            ordered = sorted(types, key=lambda t: t != hint)
            return ordered[:3]
    candidates = [hint] if hint in _AUTO_LATIN_TYPES else []
    return list(dict.fromkeys(candidates + ['english']))


def _dimension_for(encoded: NameRepr, distance_dimension: str, input_type: str) -> DistanceDimension:
    if distance_dimension == 'sound':
        order = _repr_order()
        if DistanceDimension.MP in order and encoded.mp:
            dim = DistanceDimension.MP
        elif encoded.semi:
            dim = DistanceDimension.SEMI
        else:
            dim = DistanceDimension.SPELLING
    else:
        dim_str = 'semi' if distance_dimension == 'ipa' else distance_dimension
        dim = DistanceDimension(dim_str)

    if dim in (DistanceDimension.IPA, DistanceDimension.SEMI) and encoded.semi is None:
        raise ValueError(f"Cannot use semi-phonetic distance with {input_type!r} input")
    if dim is DistanceDimension.MP and encoded.mp is None:
        raise ValueError(f"Cannot use metaphone distance with {input_type!r} input")
    return dim


def get_similar_names(input_name, input_type, distance_dimension, gender, db_path=None, hint=None):
    db_path = db_path or _DB_PATH
    if input_type == InputType.AUTO.value:
        input_types = resolve_auto_input_types(input_name, hint)
    else:
        input_types = [input_type]
    encodings = []
    for it in input_types:
        enc = _encode(input_name, InputType(it))
        encodings.append((enc, _dimension_for(enc, distance_dimension, it)))

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('PRAGMA table_info(names)')
    columns = [row[1] for row in cursor.fetchall()]
    has_original_writing = 'original_writing' in columns
    db_gender = {'male': 'boy', 'female': 'girl'}.get(gender, gender) if gender else None
    if db_gender:
        cursor.execute('SELECT * FROM names WHERE gender = ?', (db_gender,))
    else:
        cursor.execute('SELECT * FROM names')
    all_names = cursor.fetchall()
    conn.close()

    display_gender = {'boy': 'male', 'girl': 'female'}
    similar_names = []

    def _has_mp(mp: str | None) -> bool:
        if mp is None:
            return False
        s = mp.strip()
        return bool(s) and s not in {'-', '—'}

    best_score_per_encoding = [float('inf')] * len(encodings)
    for row in all_names:
        name, name_gender, name_mp, name_ipa, name_ipa_alts = row[:5]
        original_writing = row[5] if has_original_writing and len(row) > 5 else None

        scores = [
            # If we're doing MP distance, rows without MP can't be meaningfully scored.
            float('inf') if dim is DistanceDimension.MP and not _has_mp(name_mp)
            else _score(enc, dim, name, name_mp, name_ipa, name_ipa_alts)
            for enc, dim in encodings
        ]
        score = min(scores)
        if score == float('inf'):
            continue
        for i, sc in enumerate(scores):
            best_score_per_encoding[i] = min(best_score_per_encoding[i], sc)
        out_gender = display_gender.get(name_gender, name_gender)
        similar_names.append((name, out_gender, name_mp, name_ipa, name_ipa_alts, score, original_writing))

    similar_names.sort(key=lambda x: x[5])

    if not db_gender:
        seen = set()
        unique = []
        for r in similar_names:
            if r[0] not in seen:
                seen.add(r[0])
                unique.append(r)
        similar_names = unique[:10]
    else:
        similar_names = similar_names[:10]

    encoded = encodings[best_score_per_encoding.index(min(best_score_per_encoding))][0]
    return similar_names, encoded


DEFAULT_INPUT_TYPE = InputType.AUTO.value

# Latin-script names are also tried in the UI language's input type when auto-detecting.
LANG_TO_INPUT_TYPE = {
    'en': 'english', 'tr': 'turkish', 'zh': 'chinese', 'ko': 'korean',
    'hi': 'english', 'es': 'spanish', 'pt-BR': 'portuguese',
    'fr': 'french', 'fil': 'filipino', 'ja': 'japanese',
    'de': 'german', 'it': 'italian', 'ru': 'russian', 'ar': 'arabic',
    'id': 'english', 'vi': 'english',
}

UI_FLAGS = {
    'en': '🇬🇧', 'tr': '🇹🇷', 'zh': '🇨🇳', 'ko': '🇰🇷', 'hi': '🇮🇳', 'es': '🇪🇸', 'pt-BR': '🇧🇷',
    'fr': '🇫🇷', 'fil': '🇵🇭', 'ja': '🇯🇵', 'de': '🇩🇪', 'it': '🇮🇹', 'ru': '🇷🇺', 'ar': '🇸🇦',
    'id': '🇮🇩', 'vi': '🇻🇳',
}

INPUT_TYPE_OPTIONS = (
    ('english', '🇬🇧'), ('turkish', '🇹🇷'), ('chinese', '🇨🇳'), ('korean', '🇰🇷'),
    ('french', '🇫🇷'), ('filipino', '🇵🇭'), ('japanese', '🇯🇵'), ('spanish', '🇪🇸'),
    ('portuguese', '🇧🇷'), ('german', '🇩🇪'), ('italian', '🇮🇹'), ('russian', '🇷🇺'),
    ('arabic', '🇸🇦'), ('hindi', '🇮🇳'),
)
AUTO_INPUT_OPTION = ('auto', '✨')

_VALID_INPUT_TYPES = {it.value for it in InputType}
_VALID_DISTANCE_DIMENSIONS = ('sound', 'spelling', 'mp', 'ipa', 'semi')

PRODUCT_PATHS = {
    'index': '/',
    'arabic': '/my-name-in-arabic/',
    'korean': '/my-name-in-korean/',
}

POPULAR_SEARCHES = {
    'index': (
        ('Mehmet', 'turkish'), ('Ayşe', 'turkish'), ('José', 'spanish'), ('João', 'portuguese'),
        ('Jürgen', 'german'), ('Giuseppe', 'italian'), ('Дмитрий', 'russian'), ('محمد', 'arabic'),
        ('प्रिया', 'hindi'), ('François', 'french'), ('민준', 'korean'), ('Yuki', 'japanese'),
        ('Wei', 'chinese'), ('Maria', 'english'),
    ),
    'arabic': (
        ('John', 'english'), ('Michael', 'english'), ('Sarah', 'english'), ('Emily', 'english'),
        ('David', 'english'), ('Jessica', 'english'), ('Daniel', 'english'), ('Sophia', 'english'),
        ('Mehmet', 'turkish'), ('Ayşe', 'turkish'), ('José', 'spanish'), ('Дмитрий', 'russian'),
    ),
    'korean': (
        ('John', 'english'), ('Emma', 'english'), ('Michael', 'english'), ('Olivia', 'english'),
        ('James', 'english'), ('Sophia', 'english'), ('Daniel', 'english'), ('Mia', 'english'),
        ('Mehmet', 'turkish'), ('José', 'spanish'), ('Giuseppe', 'italian'), ('Дмитрий', 'russian'),
    ),
}


def _detect_input_script(text: str) -> str | None:
    text = text.strip().replace(' ', '')
    if not text:
        return None
    has_hangul = any('\uac00' <= c <= '\ud7af' for c in text)
    has_hiragana_katakana = any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text)
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
    if any('\u0400' <= c <= '\u04ff' for c in text):
        return 'russian'
    if any('\u0600' <= c <= '\u06ff' for c in text):
        return 'arabic'
    if any('\u0900' <= c <= '\u097f' for c in text):
        return 'hindi'
    if has_hangul:
        return 'korean'
    if has_hiragana_katakana:
        return 'japanese'
    if has_cjk:
        return 'chinese'
    return None


def _get_script_mismatches(input_name: str, input_type: str) -> list[str]:
    if input_type == DEFAULT_INPUT_TYPE:
        return []
    script = _detect_input_script(input_name)
    if not script or script == input_type:
        return []
    if script == 'chinese' and input_type == 'japanese':
        return []
    if script == 'chinese':
        return ['chinese', 'japanese']
    if script in LANG_TO_INPUT_TYPE.values():
        return [script]
    return []


def _get_lang():
    lang = request.args.get('lang', 'en')
    return lang if lang in LANGUAGES else 'en'


def _input_type_arg(lang: str) -> str:
    input_type = request.args.get('input_type')
    return input_type if input_type in _VALID_INPUT_TYPES else DEFAULT_INPUT_TYPE


def _hint_arg(lang: str) -> str:
    hint = request.args.get('hint')
    return hint if hint in _AUTO_LATIN_TYPES else LANG_TO_INPUT_TYPE.get(lang, 'english')


def _auto_detected_types(input_name: str, input_type: str, lang: str) -> list[str]:
    if input_type != DEFAULT_INPUT_TYPE:
        return []
    return resolve_auto_input_types(input_name, _hint_arg(lang))


def _collapse_input_type(name: str | None, input_type: str, hint: str) -> str:
    if name and input_type != DEFAULT_INPUT_TYPE and resolve_auto_input_types(name, hint) == [input_type]:
        return DEFAULT_INPUT_TYPE
    return input_type


def _distance_dimension_arg() -> str:
    dim = request.args.get('distance_dimension')
    return dim if dim in _VALID_DISTANCE_DIMENSIONS else 'sound'


def _current_product() -> str:
    for product in ('arabic', 'korean'):
        if request.path.startswith(PRODUCT_PATHS[product]):
            return product
    return 'index'


def _search_path(product: str, name: str, input_type: str, lang: str = 'en') -> str:
    input_type = _collapse_input_type(name, input_type, LANG_TO_INPUT_TYPE.get(lang, 'english'))
    params = _strip_defaults({'lang': lang, 'input_type': input_type}, lang)
    path = PRODUCT_PATHS[product] + 'find/' + quote(name, safe='')
    return path + ('?' + urlencode(params) if params else '')


def _canonical_path() -> str:
    lang = _get_lang()
    name = (request.view_args or {}).get('input_name')
    input_type = _collapse_input_type(name, _input_type_arg(lang), LANG_TO_INPUT_TYPE.get(lang, 'english'))
    params = _strip_defaults({'lang': lang, 'input_type': input_type}, lang)
    return quote(request.path, safe='/') + ('?' + urlencode(params) if params else '')


def _is_filtered_request() -> bool:
    return bool(request.args.get('gender')) or _distance_dimension_arg() != 'sound' \
        or _input_type_arg(_get_lang()) in ('ipa', 'mp')


def _strip_defaults(params: dict, lang: str = 'en') -> dict:
    defaults = {
        'lang': 'en',
        'input_type': DEFAULT_INPUT_TYPE,
        'distance_dimension': 'sound',
        'gender': '',
    }
    return {k: v for k, v in params.items() if v and v != defaults.get(k)}


def _product_url(path: str, name: str | None = None) -> str:
    base = path.rstrip('/')
    if name and name.strip():
        base = base + '/find/' + quote(name.strip(), safe='')
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    distance_dimension = _distance_dimension_arg()
    gender = request.args.get('gender') or ''
    params = _strip_defaults({
        'lang': lang,
        'input_type': _collapse_input_type(name, input_type, _hint_arg(lang)),
        'distance_dimension': distance_dimension,
        'gender': gender,
    }, lang)
    return base + ('?' + urlencode(params) if params else '')


def _product_urls(input_name: str = '') -> dict:
    name = input_name.strip() if input_name else None
    return {
        'index': _product_url('/', name),
        'arabic': _product_url('/my-name-in-arabic/', name),
        'korean': _product_url('/my-name-in-korean/', name),
    }


def _lang_url(lang_code):
    args = request.args.to_dict()
    args['lang'] = lang_code
    args['input_type'] = DEFAULT_INPUT_TYPE
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa', 'semi') else 'sound'
    args = _strip_defaults(args, lang_code)
    return request.path + ('?' + urlencode(args) if args else '')


@app.route('/')
def index():
    lang = _get_lang()
    t = get_translations(lang)
    lang_links = [(code, label, _lang_url(code)) for code, (label, _) in LANGUAGES.items()]
    input_type = _input_type_arg(lang)
    input_name = unquote(request.args.get('name', '') or '')
    return render_template(
        'index.html', t=t, lang=lang, languages=LANGUAGES, lang_links=lang_links,
        input_type=input_type,
        distance_dimension=_distance_dimension_arg(),
        gender=request.args.get('gender', ''),
        script_mismatches=[],
        mismatch_cta_links=[],
        product_urls=_product_urls(input_name),
        input_name=input_name,
    )


@app.route('/find', methods=['GET'])
def find_redirect():
    input_name = request.args.get('name')
    input_name = unquote(input_name or '')
    if not input_name:
        lang = request.args.get('lang', 'en')
        params = _strip_defaults({'lang': lang, 'input_type': DEFAULT_INPUT_TYPE}, lang)
        return redirect(url_for('index', **params))
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    params = _strip_defaults({
        'input_type': _collapse_input_type(input_name, input_type, _hint_arg(lang)),
        'distance_dimension': _distance_dimension_arg(),
        'gender': request.args.get('gender') or '',
        'lang': lang,
        'hint': request.args.get('hint') if request.args.get('hint') in _AUTO_LATIN_TYPES else '',
    }, lang)
    return redirect(url_for('find_similar_names_pretty', input_name=input_name, **params))


@app.route('/find/<string:input_name>', methods=['GET'])
def find_similar_names_pretty(input_name):
    input_name = unquote(input_name)
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    distance_dimension = _distance_dimension_arg()
    gender = request.args.get('gender') or ''
    t = get_translations(lang)

    similar_names, input_fields = get_similar_names(input_name, input_type, distance_dimension, gender, hint=_hint_arg(lang))

    script_mismatches = _get_script_mismatches(input_name, input_type)
    mismatch_cta_links = []
    for suggested_type in script_mismatches:
        args = _strip_defaults(request.args.to_dict(), lang)
        args['input_type'] = suggested_type
        stripped = _strip_defaults(args, lang)
        mismatch_cta_links.append((suggested_type, request.path + ('?' + urlencode(stripped) if stripped else '')))

    page_title = t['page_title']
    meta_description = t['meta_description']
    if input_name:
        page_title = f"{t['similar_to'].format(name=input_name)} - {t['page_title']}"
        meta_description = t.get('results_meta_description', t['meta_description']).format(name=input_name)

    return render_template(
        'index.html',
        input_name=input_name,
        input_type=input_type,
        input_fields=input_fields,
        similar_names=similar_names,
        distance_dimension=distance_dimension,
        gender=gender,
        page_title=page_title,
        meta_description=meta_description,
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=[(code, label, _lang_url(code)) for code, (label, _) in LANGUAGES.items()],
        script_mismatches=script_mismatches,
        detected_input_types=_auto_detected_types(input_name, input_type, lang),
        mismatch_cta_links=mismatch_cta_links,
        product_urls=_product_urls(input_name),
        noindex=not similar_names,
    )


def _kr_lang_url(lang_code):
    args = request.args.to_dict()
    args['lang'] = lang_code
    args['input_type'] = DEFAULT_INPUT_TYPE
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa', 'semi') else 'sound'
    args = _strip_defaults(args, lang_code)
    path = request.path if request.path.startswith('/my-name-in-korean/find') else '/my-name-in-korean/'
    return path + ('?' + urlencode(args) if args else '')


def _ar_lang_url(lang_code):
    args = request.args.to_dict()
    args['lang'] = lang_code
    args['input_type'] = DEFAULT_INPUT_TYPE
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa', 'semi') else 'sound'
    args = _strip_defaults(args, lang_code)
    path = request.path if request.path.startswith('/my-name-in-arabic/find') else '/my-name-in-arabic/'
    return path + ('?' + urlencode(args) if args else '')


@app.route('/my-name-in-arabic/')
def arabic_index():
    lang = _get_lang()
    t = get_arabic_page_translations(lang)
    lang_links = [(code, label, _ar_lang_url(code)) for code, (label, _) in LANGUAGES.items()]
    input_type = _input_type_arg(lang)
    input_name = unquote(request.args.get('name', '') or '')
    return render_template(
        'arabic.html',
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=lang_links,
        input_type=input_type,
        distance_dimension=_distance_dimension_arg(),
        gender=request.args.get('gender', ''),
        script_mismatches=[],
        mismatch_cta_links=[],
        product_urls=_product_urls(input_name),
        input_name=input_name,
    )


@app.route('/my-name-in-arabic/find', methods=['GET'])
def arabic_find_redirect():
    input_name = request.args.get('name')
    input_name = unquote(input_name or '')
    if not input_name:
        lang = request.args.get('lang', 'en')
        params = _strip_defaults({'lang': lang, 'input_type': DEFAULT_INPUT_TYPE}, lang)
        return redirect(url_for('arabic_index', **params))
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    params = _strip_defaults({
        'input_type': _collapse_input_type(input_name, input_type, _hint_arg(lang)),
        'distance_dimension': _distance_dimension_arg(),
        'gender': request.args.get('gender') or '',
        'lang': lang,
        'hint': request.args.get('hint') if request.args.get('hint') in _AUTO_LATIN_TYPES else '',
    }, lang)
    return redirect(url_for('find_similar_arabic_names', input_name=input_name, **params))


@app.route('/my-name-in-arabic/find/<string:input_name>', methods=['GET'])
def find_similar_arabic_names(input_name):
    input_name = unquote(input_name)
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    distance_dimension = _distance_dimension_arg()
    gender = request.args.get('gender') or ''
    t = get_arabic_page_translations(lang)

    similar_names, input_fields = get_similar_names(
        input_name, input_type, distance_dimension, gender, db_path=_ARAB_DB_PATH, hint=_hint_arg(lang)
    )

    script_mismatches = _get_script_mismatches(input_name, input_type)
    mismatch_cta_links = []
    for suggested_type in script_mismatches:
        args = _strip_defaults(request.args.to_dict(), lang)
        args['input_type'] = suggested_type
        stripped = _strip_defaults(args, lang)
        mismatch_cta_links.append((suggested_type, request.path + ('?' + urlencode(stripped) if stripped else '')))

    page_title = t['page_title']
    meta_description = t['meta_description']
    if input_name:
        page_title = f"{t['similar_to'].format(name=input_name)} - {t['page_title']}"
        meta_description = t.get('results_meta_description', t['meta_description']).format(name=input_name)

    return render_template(
        'arabic.html',
        input_name=input_name,
        input_type=input_type,
        input_fields=input_fields,
        similar_names=similar_names,
        distance_dimension=distance_dimension,
        gender=gender,
        page_title=page_title,
        meta_description=meta_description,
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=[(code, label, _ar_lang_url(code)) for code, (label, _) in LANGUAGES.items()],
        script_mismatches=script_mismatches,
        detected_input_types=_auto_detected_types(input_name, input_type, lang),
        mismatch_cta_links=mismatch_cta_links,
        product_urls=_product_urls(input_name),
        noindex=not similar_names,
    )


@app.route('/my-name-in-korean/')
def korean_index():
    lang = _get_lang()
    t = get_korean_page_translations(lang)
    lang_links = [(code, label, _kr_lang_url(code)) for code, (label, _) in LANGUAGES.items()]
    input_type = _input_type_arg(lang)
    input_name = unquote(request.args.get('name', '') or '')
    return render_template(
        'korean.html',
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=lang_links,
        input_type=input_type,
        distance_dimension=_distance_dimension_arg(),
        gender=request.args.get('gender', ''),
        script_mismatches=[],
        mismatch_cta_links=[],
        product_urls=_product_urls(input_name),
        input_name=input_name,
    )


@app.route('/my-name-in-korean/find', methods=['GET'])
def korean_find_redirect():
    input_name = request.args.get('name')
    input_name = unquote(input_name or '')
    if not input_name:
        lang = request.args.get('lang', 'en')
        params = _strip_defaults({'lang': lang, 'input_type': DEFAULT_INPUT_TYPE}, lang)
        return redirect(url_for('korean_index', **params))
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    params = _strip_defaults({
        'input_type': _collapse_input_type(input_name, input_type, _hint_arg(lang)),
        'distance_dimension': _distance_dimension_arg(),
        'gender': request.args.get('gender') or '',
        'lang': lang,
        'hint': request.args.get('hint') if request.args.get('hint') in _AUTO_LATIN_TYPES else '',
    }, lang)
    return redirect(url_for('find_similar_korean_names', input_name=input_name, **params))


@app.route('/my-name-in-korean/find/<string:input_name>', methods=['GET'])
def find_similar_korean_names(input_name):
    input_name = unquote(input_name)
    lang = _get_lang()
    input_type = _input_type_arg(lang)
    distance_dimension = _distance_dimension_arg()
    gender = request.args.get('gender') or ''
    t = get_korean_page_translations(lang)

    similar_names, input_fields = get_similar_names(
        input_name, input_type, distance_dimension, gender, db_path=_KOREAN_DB_PATH, hint=_hint_arg(lang)
    )

    script_mismatches = _get_script_mismatches(input_name, input_type)
    mismatch_cta_links = []
    for suggested_type in script_mismatches:
        args = _strip_defaults(request.args.to_dict(), lang)
        args['input_type'] = suggested_type
        stripped = _strip_defaults(args, lang)
        mismatch_cta_links.append((suggested_type, request.path + ('?' + urlencode(stripped) if stripped else '')))

    page_title = t['page_title']
    meta_description = t['meta_description']
    if input_name:
        page_title = f"{t['similar_to'].format(name=input_name)} - {t['page_title']}"
        meta_description = t.get('results_meta_description', t['meta_description']).format(name=input_name)

    return render_template(
        'korean.html',
        input_name=input_name,
        input_type=input_type,
        input_fields=input_fields,
        similar_names=similar_names,
        distance_dimension=distance_dimension,
        gender=gender,
        page_title=page_title,
        meta_description=meta_description,
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=[(code, label, _kr_lang_url(code)) for code, (label, _) in LANGUAGES.items()],
        script_mismatches=script_mismatches,
        detected_input_types=_auto_detected_types(input_name, input_type, lang),
        mismatch_cta_links=mismatch_cta_links,
        product_urls=_product_urls(input_name),
        noindex=not similar_names,
    )


@app.route('/robots.txt')
def robots_txt():
    body = f"User-agent: *\nAllow: /\n\nSitemap: {_BASE_URL}/sitemap.xml\n"
    return Response(body, mimetype='text/plain')


def _sitemap_paths() -> list[str]:
    paths: list[str] = []
    for product, home in PRODUCT_PATHS.items():
        for lang in LANGUAGES:
            params = _strip_defaults({'lang': lang}, lang)
            paths.append(home + ('?' + urlencode(params) if params else ''))
        for lang in LANGUAGES:
            for name, input_type in POPULAR_SEARCHES[product]:
                paths.append(_search_path(product, name, input_type, lang))

    def distinct(db_path: str, column: str) -> list[str]:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(f'SELECT DISTINCT {column} FROM names WHERE {column} IS NOT NULL ORDER BY {column}').fetchall()
        finally:
            conn.close()
        return [r[0].strip() for r in rows if r[0] and r[0].strip()]

    for name in distinct(_DB_PATH, 'name'):
        paths.append(_search_path('arabic', name.title(), 'english'))
        paths.append(_search_path('korean', name.title(), 'english'))
    for name in distinct(_ARAB_DB_PATH, 'original_writing'):
        paths.append(_search_path('index', name, 'arabic'))
    for name in distinct(_KOREAN_DB_PATH, 'original_writing'):
        if _detect_input_script(name) == 'korean':
            paths.append(_search_path('index', name, 'korean'))
    return list(dict.fromkeys(paths))


@app.route('/sitemap.xml')
def sitemap_xml():
    urls = ''.join(f'<url><loc>{escape(_BASE_URL + p)}</loc></url>' for p in _sitemap_paths())
    body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(body, mimetype='application/xml')


if __name__ == '__main__':
    if os.environ.get('VERCEL', None):
        app.run(debug=False, host="0.0.0.0", port=8443)
    else:
        app.run(debug=True)
