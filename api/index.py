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
from jellyfish import jaro_winkler_similarity
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
    MP = 'mp'
    SOUND = 'sound'
    SPELLING = 'spelling'


@dataclass
class NameRepr:
    name: str
    ipa: str | None = None
    mp: str | None = None


def _distance(x, y):
    return 1 - jaro_winkler_similarity(x, y)


def _encode_romanized(name: str) -> NameRepr:
    normalized = name.capitalize()
    ipa_result = ipa_list(normalized)
    ipa = ipa_result[0][0] if ipa_result else None
    mp = doublemetaphone(normalized)[0].upper() if doublemetaphone(normalized)[0] else None
    return NameRepr(name, ipa=ipa, mp=mp)


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


def _encode_pinyin(name: str) -> NameRepr | None:
    try:
        from pinyin_to_ipa import pinyin_to_ipa
    except ImportError:
        return None
    pinyin_str = name.lower().strip()
    if any('\u4e00' <= c <= '\u9fff' for c in name):
        pinyin_str = _chinese_to_pinyin(name)
        if not pinyin_str:
            return None
    parts = pinyin_str.split()
    ipa_parts = []
    for part in parts:
        try:
            result = pinyin_to_ipa(part)
            if not result:
                return None
            first = list(result)[0]
            ipa_parts.append(''.join(str(x) for x in first))
        except Exception:
            return None
    if not ipa_parts:
        return None
    ipa = ''.join(ipa_parts)
    mp = mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P')
    return NameRepr(name, ipa=ipa, mp=mp)


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
    match input_type:
        case InputType.ENGLISH:
            return _encode_romanized(name)
        case InputType.TURKISH:
            ipa = mhelp.turkish_to_ipa(name)
            mp = mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P')
            return NameRepr(name, ipa=ipa, mp=mp)
        case InputType.FRENCH:
            ipa = mhelp.french_to_ipa(name)
            mp = mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P')
            return NameRepr(name, ipa=ipa, mp=mp)
        case InputType.CHINESE:
            encoded = _encode_pinyin(name)
            return encoded if encoded else _encode_romanized(name)
        case InputType.KOREAN:
            romanized = _hangul_to_phonetic_romanization(name)
            if romanized:
                enc = _encode_romanized(romanized)
                return NameRepr(name, ipa=enc.ipa, mp=enc.mp)
            return _encode_romanized(name)
        case InputType.JAPANESE:
            romaji = _japanese_to_romaji(name)
            if romaji:
                enc = _encode_romanized(romaji)
                return NameRepr(name, ipa=enc.ipa, mp=enc.mp)
            return _encode_romanized(name)
        case InputType.FILIPINO:
            return _encode_romanized(name)
        case InputType.IPA:
            return NameRepr(name, ipa=name)
        case InputType.MP:
            return NameRepr(name, mp=name.upper())
        case _ as unreachable:
            assert_never(unreachable)


_CONSONANTS = set('BCDFGHJKLMNPQRSTVWXYZ0')

def _first_letter_penalty(input_mp: str, name_mp: str, weight: float = 0.15) -> float:
    if not input_mp or not name_mp:
        return 0.0
    first_in, first_db = input_mp[0].upper(), name_mp[0].upper()
    if first_in not in _CONSONANTS:
        return 0.0
    return 0.0 if first_in == first_db else weight


def _phonetic_score(primary_input, primary_db, secondary_input, secondary_db, primary_is_mp=False, input_name=None, db_name=None):
    score = _distance(primary_input, primary_db)
    if secondary_input and secondary_db:
        score += _distance(secondary_input, secondary_db) / 100
    if input_name and db_name:
        score += _spelling_score(input_name, db_name) / 10000
    if primary_is_mp and primary_input and primary_db:
        score += _first_letter_penalty(primary_input, primary_db)
    return score


def _strip_diacritics(text):
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def _spelling_score(input_name, name):
    a = re.sub(r'(.)\1+', r'\1', _strip_diacritics(input_name.lower()))
    b = re.sub(r'(.)\1+', r'\1', _strip_diacritics(name.lower()))
    return _distance(a, b)


app = Flask(__name__)


@app.context_processor
def _inject_lang_default_input_type():
    lang = request.args.get('lang', 'en')
    return {'lang_default_input_type': LANG_TO_INPUT_TYPE.get(lang, 'english')}


def _score(encoded, dim, name, name_mp, name_ipa):
    match dim:
        case DistanceDimension.IPA:
            return _phonetic_score(encoded.ipa, name_ipa, encoded.mp, name_mp, input_name=encoded.name, db_name=name)
        case DistanceDimension.MP:
            return _phonetic_score(encoded.mp, name_mp, encoded.ipa, name_ipa, primary_is_mp=True, input_name=encoded.name, db_name=name)
        case DistanceDimension.SPELLING:
            return _spelling_score(encoded.name, name)
        case _ as unreachable:
            assert_never(unreachable)


def get_similar_names(input_name, input_type, distance_dimension, gender, db_path=None):
    db_path = db_path or _DB_PATH
    encoded = _encode(input_name, InputType(input_type))

    if distance_dimension == 'sound':
        dim = DistanceDimension.MP if encoded.mp else DistanceDimension.IPA
    else:
        dim = DistanceDimension(distance_dimension)

    if dim is DistanceDimension.IPA and encoded.ipa is None:
        raise ValueError(f"Cannot use IPA distance with {input_type!r} input")
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
    for row in all_names:
        name, name_gender, name_mp, name_ipa, name_ipa_alts = row[:5]
        original_writing = row[5] if has_original_writing and len(row) > 5 else None
        score = _score(encoded, dim, name, name_mp, name_ipa)
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
    if distance_dimension not in ('sound', 'mp', 'ipa'):
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
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa') else 'sound'
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
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa') else 'sound'
    args = _strip_defaults(args, lang_code)
    path = request.path if request.path.startswith('/my-name-in-korean/find') else '/my-name-in-korean/'
    return path + ('?' + urlencode(args) if args else '')


def _ar_lang_url(lang_code):
    args = request.args.to_dict()
    args['lang'] = lang_code
    args['input_type'] = LANG_TO_INPUT_TYPE.get(lang_code, 'english')
    args['distance_dimension'] = args.get('distance_dimension') if args.get('distance_dimension') in ('sound', 'mp', 'ipa') else 'sound'
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
