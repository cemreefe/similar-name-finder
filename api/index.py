from dataclasses import dataclass
from enum import Enum
from typing import assert_never
from flask import Flask, render_template, request, redirect, url_for
try:
    from api.translations import get_translations, get_arabic_page_translations, get_korean_page_translations, LANGUAGES
except ImportError:
    from translations import get_translations, get_arabic_page_translations, get_korean_page_translations, LANGUAGES
import sqlite3
from metaphone import doublemetaphone
import helpers.metaphone_helper as mhelp
from eng_to_ipa import ipa_list
from jellyfish import jaro_winkler_similarity, damerau_levenshtein_distance
import os
from urllib.parse import quote, unquote, urlencode

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

            case (InputType.TURKISH | InputType.FRENCH, DistanceDimension.MP):
                ipa = cached_ipa if cached_ipa is not None else _transform(s, it, DistanceDimension.IPA)
                return mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P') if ipa else None
            case (InputType.CHINESE, DistanceDimension.MP):
                ipa = cached_ipa if cached_ipa is not None else _transform(s, it, DistanceDimension.IPA)
                return mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P') if ipa else romanized_mp(s)
            case (InputType.ENGLISH | InputType.FILIPINO, DistanceDimension.MP):
                return romanized_mp(s)
            case (InputType.KOREAN, DistanceDimension.MP):
                romanized = korean_romanized(s)
                return romanized_mp(romanized) if romanized else romanized_mp(s)
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
    return {'lang_default_input_type': LANG_TO_INPUT_TYPE.get(lang, 'english')}


def _score(encoded: NameRepr, dim: DistanceDimension, name: str, name_mp: str | None, name_ipa: str | None, name_ipa_alts: str | None) -> float:
    if dim is DistanceDimension.SPELLING:
        return _spelling_score(encoded.name, name)

    primary = DistanceDimension.MP if dim is DistanceDimension.MP else DistanceDimension.SEMI
    order = [primary] + [x for x in _repr_order() if x is not primary]
    return _score_with_order(encoded, primary, order, name, name_mp, name_ipa, name_ipa_alts)


def get_similar_names(input_name, input_type, distance_dimension, gender, db_path=None):
    db_path = db_path or _DB_PATH
    encoded = _encode(input_name, InputType(input_type))

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

    for row in all_names:
        name, name_gender, name_mp, name_ipa, name_ipa_alts = row[:5]
        original_writing = row[5] if has_original_writing and len(row) > 5 else None

        # If we're doing MP distance, rows without MP can't be meaningfully scored.
        if dim is DistanceDimension.MP and not _has_mp(name_mp):
            continue

        score = _score(encoded, dim, name, name_mp, name_ipa, name_ipa_alts)
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

    return similar_names, encoded


LANG_TO_INPUT_TYPE = {
    'en': 'english', 'tr': 'turkish', 'zh': 'chinese', 'ko': 'korean',
    'hi': 'english', 'es': 'english', 'pt-BR': 'english',
    'fr': 'french', 'fil': 'filipino', 'ja': 'japanese',
}


def _detect_input_script(text: str) -> str | None:
    text = text.strip().replace(' ', '')
    if not text:
        return None
    has_hangul = any('\uac00' <= c <= '\ud7af' for c in text)
    has_hiragana_katakana = any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text)
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
    if has_hangul:
        return 'korean'
    if has_hiragana_katakana:
        return 'japanese'
    if has_cjk:
        return 'chinese'
    return None


def _get_script_mismatches(input_name: str, input_type: str) -> list[str]:
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


def _strip_defaults(params: dict, lang: str = 'en') -> dict:
    defaults = {
        'lang': 'en',
        'input_type': LANG_TO_INPUT_TYPE.get(lang, 'english'),
        'distance_dimension': 'sound',
        'gender': '',
    }
    return {k: v for k, v in params.items() if v and v != defaults.get(k)}


def _product_url(path: str, name: str | None = None) -> str:
    base = path.rstrip('/')
    if name and name.strip():
        base = base + '/find/' + quote(name.strip(), safe='')
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    distance_dimension = request.args.get('distance_dimension') or 'sound'
    if distance_dimension not in ('sound', 'mp', 'ipa', 'semi'):
        distance_dimension = 'sound'
    gender = request.args.get('gender') or ''
    params = _strip_defaults({
        'lang': lang,
        'input_type': input_type,
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
    args['input_type'] = LANG_TO_INPUT_TYPE.get(lang_code, 'english')
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa', 'semi') else 'sound'
    args = _strip_defaults(args, lang_code)
    return request.path + ('?' + urlencode(args) if args else '')


@app.route('/')
def index():
    lang = _get_lang()
    t = get_translations(lang)
    lang_links = [(code, label, _lang_url(code)) for code, (label, _) in LANGUAGES.items()]
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    input_name = unquote(request.args.get('name', '') or '')
    return render_template(
        'index.html', t=t, lang=lang, languages=LANGUAGES, lang_links=lang_links,
        input_type=input_type,
        distance_dimension=request.args.get('distance_dimension', 'sound'),
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
        params = _strip_defaults({'lang': lang, 'input_type': LANG_TO_INPUT_TYPE.get(lang, 'english')}, lang)
        return redirect(url_for('index', **params))
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    params = _strip_defaults({
        'input_type': input_type,
        'distance_dimension': request.args.get('distance_dimension') or 'sound',
        'gender': request.args.get('gender') or '',
        'lang': lang,
    }, lang)
    return redirect(url_for('find_similar_names_pretty', input_name=input_name, **params))


@app.route('/find/<string:input_name>', methods=['GET'])
def find_similar_names_pretty(input_name):
    input_name = unquote(input_name)
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    distance_dimension = request.args.get('distance_dimension') or 'sound'
    gender = request.args.get('gender') or ''
    t = get_translations(lang)

    similar_names, input_fields = get_similar_names(input_name, input_type, distance_dimension, gender)

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
        mismatch_cta_links=mismatch_cta_links,
        product_urls=_product_urls(input_name),
    )


def _kr_lang_url(lang_code):
    args = request.args.to_dict()
    args['lang'] = lang_code
    args['input_type'] = LANG_TO_INPUT_TYPE.get(lang_code, 'english')
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa', 'semi') else 'sound'
    args = _strip_defaults(args, lang_code)
    path = request.path if request.path.startswith('/my-name-in-korean/find') else '/my-name-in-korean/'
    return path + ('?' + urlencode(args) if args else '')


def _ar_lang_url(lang_code):
    args = request.args.to_dict()
    args['lang'] = lang_code
    args['input_type'] = LANG_TO_INPUT_TYPE.get(lang_code, 'english')
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa', 'semi') else 'sound'
    args = _strip_defaults(args, lang_code)
    path = request.path if request.path.startswith('/my-name-in-arabic/find') else '/my-name-in-arabic/'
    return path + ('?' + urlencode(args) if args else '')


@app.route('/my-name-in-arabic/')
def arabic_index():
    lang = _get_lang()
    t = get_arabic_page_translations(lang)
    lang_links = [(code, label, _ar_lang_url(code)) for code, (label, _) in LANGUAGES.items()]
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    input_name = unquote(request.args.get('name', '') or '')
    return render_template(
        'arabic.html',
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=lang_links,
        input_type=input_type,
        distance_dimension=request.args.get('distance_dimension', 'sound'),
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
        params = _strip_defaults({'lang': lang, 'input_type': LANG_TO_INPUT_TYPE.get(lang, 'english')}, lang)
        return redirect(url_for('arabic_index', **params))
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    params = _strip_defaults({
        'input_type': input_type,
        'distance_dimension': request.args.get('distance_dimension') or 'sound',
        'gender': request.args.get('gender') or '',
        'lang': lang,
    }, lang)
    return redirect(url_for('find_similar_arabic_names', input_name=input_name, **params))


@app.route('/my-name-in-arabic/find/<string:input_name>', methods=['GET'])
def find_similar_arabic_names(input_name):
    input_name = unquote(input_name)
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    distance_dimension = request.args.get('distance_dimension') or 'sound'
    gender = request.args.get('gender') or ''
    t = get_arabic_page_translations(lang)

    similar_names, input_fields = get_similar_names(
        input_name, input_type, distance_dimension, gender, db_path=_ARAB_DB_PATH
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
        mismatch_cta_links=mismatch_cta_links,
        product_urls=_product_urls(input_name),
    )


@app.route('/my-name-in-korean/')
def korean_index():
    lang = _get_lang()
    t = get_korean_page_translations(lang)
    lang_links = [(code, label, _kr_lang_url(code)) for code, (label, _) in LANGUAGES.items()]
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    input_name = unquote(request.args.get('name', '') or '')
    return render_template(
        'korean.html',
        t=t,
        lang=lang,
        languages=LANGUAGES,
        lang_links=lang_links,
        input_type=input_type,
        distance_dimension=request.args.get('distance_dimension', 'sound'),
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
        params = _strip_defaults({'lang': lang, 'input_type': LANG_TO_INPUT_TYPE.get(lang, 'english')}, lang)
        return redirect(url_for('korean_index', **params))
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    params = _strip_defaults({
        'input_type': input_type,
        'distance_dimension': request.args.get('distance_dimension') or 'sound',
        'gender': request.args.get('gender') or '',
        'lang': lang,
    }, lang)
    return redirect(url_for('find_similar_korean_names', input_name=input_name, **params))


@app.route('/my-name-in-korean/find/<string:input_name>', methods=['GET'])
def find_similar_korean_names(input_name):
    input_name = unquote(input_name)
    lang = _get_lang()
    input_type = request.args.get('input_type') or LANG_TO_INPUT_TYPE.get(lang, 'english')
    distance_dimension = request.args.get('distance_dimension') or 'sound'
    gender = request.args.get('gender') or ''
    t = get_korean_page_translations(lang)

    similar_names, input_fields = get_similar_names(
        input_name, input_type, distance_dimension, gender, db_path=_KOREAN_DB_PATH
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
        mismatch_cta_links=mismatch_cta_links,
        product_urls=_product_urls(input_name),
    )


if __name__ == '__main__':
    if os.environ.get('VERCEL', None):
        app.run(debug=False, host="0.0.0.0", port=8443)
    else:
        app.run(debug=True)
