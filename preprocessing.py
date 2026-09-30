import csv
import os
import re
import unicodedata
import sqlite3
from tqdm import tqdm
from pypinyin import pinyin, Style
from metaphone import doublemetaphone
from eng_to_ipa import ipa_list

from helpers import metaphone_helper as mhelp
from helpers.metaphone_helper import hangul_to_metaphone, hangul_to_phonetic_romanization
from api.index import InputType, NameRepr, _encode, _japanese_to_romaji

KOREAN_TWO_CHAR_SURNAMES = frozenset([
    '남궁', '사공', '제갈', '선우', '독고', '동방', '서문', '황보', '등정', '망절', '무본',
])

MIN_POPULARITY_THRESHOLD = 0.0005  # 0.05% — exclude names below this max popularity

EXCLUDE_FROM_ENGLISH = frozenset([
    'aaliyah', 'abdul', 'abdullah', 'ahmad', 'ahmed', 'aisha', 'akeem', 'ala',
    'ali', 'alia', 'amani', 'amin', 'amina', 'amir', 'amira', 'amirah',
    'anwar', 'ayaan', 'ayesha', 'bilal', 'daneen', 'dema', 'diya', 'farah',
    'fatima', 'hakeem', 'hakim', 'hamza', 'hasan', 'hassan', 'ibrahim',
    'imani', 'isa', 'isam', 'jabbar', 'jaleel', 'jamal', 'jameel', 'jamil',
    'jamila', 'kadin', 'kamilah', 'kareem', 'karim', 'khadijah', 'khalid',
    'khalil', 'khalilah', 'latifah', 'maira', 'malik', 'mariam', 'mariyah',
    'maryam', 'mohammed', 'muhammad', 'mustafa', 'nada', 'naima', 'nakia',
    'nasir', 'omar', 'rakeem', 'rashad', 'rasheed', 'rashida', 'rayan',
    'salma', 'samir', 'samira', 'sanaa', 'saniya', 'saniyah', 'sharif',
    'syed', 'taj', 'tariq', 'yasmeen', 'yasmin', 'yasmine', 'yusuf', 'zaid',
    'zaida', 'zain',
])


def split_korean_name(korean: str) -> tuple[str, str] | None:
    """Split Hangul name into (family, given). Returns None for non-standard names (e.g. Western)."""
    korean = korean.strip()
    if not korean or ' ' in korean:
        return None
    if not all('\uac00' <= c <= '\ud7af' for c in korean):
        return None
    if len(korean) < 2:
        return None
    if korean[:2] in KOREAN_TWO_CHAR_SURNAMES and len(korean) > 2:
        return korean[:2], korean[2:]
    return korean[0], korean[1:]


def calculate_phonetic_representation(name):
    return doublemetaphone(name)[0]


def _arabic_friendly_metaphone(name):
    """Double Metaphone drops J after vowels (English-centric). Replace j→zh to preserve it."""
    fixed = name.replace('j', 'zh').replace('J', 'Zh')
    return doublemetaphone(fixed)[0]

# Function to calculate IPA transcription of a name
def calculate_ipa_transcription(name):
    ipa = ipa_list(name)[0]
    if ipa:
        ipa_transcription = ipa[0]
        ipa_alternatives = ','.join(ipa[1:])
        return ipa_transcription, ipa_alternatives
    else:
        return None, None

def _compute_max_popularity(csv_file):
    from collections import defaultdict
    name_max_pct = defaultdict(float)
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)
        for row in reader:
            name = row[1].lower()
            pct = float(row[2])
            if pct > name_max_pct[name]:
                name_max_pct[name] = pct
    return name_max_pct


def create_database(csv_file, db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS names (
                        name TEXT,
                        gender TEXT,
                        phonetic_representation TEXT,
                        ipa_transcription TEXT,
                        ipa_alternatives TEXT,
                        PRIMARY KEY (name, gender)
                    )''')

    name_max_pct = _compute_max_popularity(csv_file)
    excluded = EXCLUDE_FROM_ENGLISH | {
        n for n, p in name_max_pct.items() if p < MIN_POPULARITY_THRESHOLD
    }
    print(f"Excluding {len(excluded)} names ({len(EXCLUDE_FROM_ENGLISH)} explicit + "
          f"{len(excluded) - len(EXCLUDE_FROM_ENGLISH)} below {MIN_POPULARITY_THRESHOLD*100:.2f}% popularity)")

    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)
        total_rows = sum(1 for row in reader)
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)
        for row in tqdm(reader, total=total_rows, desc="Processing CSV"):
            name = row[1]
            gender = row[3]
            if name.lower() in excluded:
                continue
            phonetic_repr = calculate_phonetic_representation(name)
            ipa_transcription, ipa_alternatives = calculate_ipa_transcription(name)
            try:
                cursor.execute('''INSERT INTO names (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives)
                                VALUES (?, ?, ?, ?, ?)''', (name, gender, phonetic_repr, ipa_transcription, ipa_alternatives))
            except sqlite3.IntegrityError:
                pass

    conn.commit()
    conn.close()


def _normalize_for_lookup(s):
    return ''.join(c for c in s.lower().replace("'", "").replace("'", " ") if c.isalnum() or c == ' ').replace(' ', '')


def _load_arabic_writings_lookup(csv_path, eng_col='english_name', arabic_col='arabic_name'):
    lookup = {}
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            eng = row.get(eng_col, '').strip()
            arabic = row.get(arabic_col, '').strip()
            if not eng or not arabic:
                continue
            key = _normalize_for_lookup(eng.replace(' 1', '').replace(' 2', '').replace(' 3', ''))
            if key and key not in lookup:
                lookup[key] = arabic
    return lookup


def _merge_arabic_lookups(*lookups):
    merged = {}
    for lookup in lookups:
        for k, v in lookup.items():
            if k not in merged:
                merged[k] = v
    return merged


def create_arabic_database(csv_file, db_file, arabic_writings_csv=None, ar_en_names_csv=None):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS names (
                        name TEXT,
                        gender TEXT,
                        phonetic_representation TEXT,
                        ipa_transcription TEXT,
                        ipa_alternatives TEXT,
                        original_writing TEXT,
                        PRIMARY KEY (name, gender)
                    )''')
    cursor.execute('DELETE FROM names')

    lookups = []
    if arabic_writings_csv and os.path.exists(arabic_writings_csv):
        lookups.append(_load_arabic_writings_lookup(arabic_writings_csv))
    if ar_en_names_csv and os.path.exists(ar_en_names_csv):
        lookups.append(_load_arabic_writings_lookup(ar_en_names_csv, eng_col='english', arabic_col='arabic'))
    arabic_lookup = _merge_arabic_lookups(*lookups)

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in tqdm(rows, desc="Processing Arabic CSV"):
        name = row.get('Name', row.get('english_name', '')).strip()
        if not name:
            continue
        gender = row.get('Gender', row.get('gender', 'm'))
        gender = 'boy' if str(gender).lower() in ('m', 'male') else 'girl'
        original_writing = arabic_lookup.get(_normalize_for_lookup(name)) if arabic_lookup else None
        phonetic_repr = _arabic_friendly_metaphone(name)
        ipa_transcription, ipa_alternatives = calculate_ipa_transcription(name)
        try:
            cursor.execute('''INSERT INTO names (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives, original_writing)
                            VALUES (?, ?, ?, ?, ?, ?)''', (name, gender, phonetic_repr, ipa_transcription, ipa_alternatives, original_writing))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


def create_korean_database(csv_file, db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS names (
                        name TEXT,
                        gender TEXT,
                        phonetic_representation TEXT,
                        ipa_transcription TEXT,
                        ipa_alternatives TEXT,
                        original_writing TEXT,
                        PRIMARY KEY (name, gender)
                    )''')
    cursor.execute('DELETE FROM names')

    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
    for row in tqdm(rows, desc="Processing Korean CSV"):
        korean = row.get('Korean Name', '').strip()
        gender = 'boy' if row.get('Gender', 'M').upper() == 'M' else 'girl'
        if not korean:
            continue
        split = split_korean_name(korean)
        if split is None:
            continue
        _, given_hangul = split
        romanized = hangul_to_phonetic_romanization(given_hangul)
        if not romanized:
            continue
        name = romanized.replace(' ', '').title()
        phonetic_repr = hangul_to_metaphone(given_hangul)
        if phonetic_repr is None:
            phonetic_repr = calculate_phonetic_representation(name)
        ipa_transcription, ipa_alternatives = calculate_ipa_transcription(name)
        try:
            cursor.execute('''INSERT INTO names (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives, original_writing)
                            VALUES (?, ?, ?, ?, ?, ?)''', (name, gender, phonetic_repr, ipa_transcription, ipa_alternatives, given_hangul))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


def _turkish_title(name: str) -> str:
    """Title-case Turkish names without turning initial i into an ASCII I."""
    def title_word(word: str) -> str:
        if not word:
            return word
        first = {'i': 'İ', 'ı': 'I'}.get(word[0], word[0].upper())
        return first + word[1:]

    return ' '.join(title_word(word) for word in name.strip().split())


def create_turkish_database(csv_file, db_file):
    """Build a Turkish-name database from the MIT-licensed source CSV."""
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS names (
                        name TEXT,
                        gender TEXT,
                        phonetic_representation TEXT,
                        ipa_transcription TEXT,
                        ipa_alternatives TEXT,
                        PRIMARY KEY (name, gender)
                    )''')
    cursor.execute('DELETE FROM names')

    with open(csv_file, 'r', encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    gender_map = {'E': ('boy',), 'K': ('girl',), 'U': ('boy', 'girl')}
    for row in tqdm(rows, desc='Processing Turkish CSV'):
        raw_name = (row.get('name') or '').strip()
        genders = gender_map.get((row.get('sex') or '').strip().upper())
        if not raw_name or not genders:
            continue

        name = _turkish_title(raw_name)
        ipa_transcription = mhelp.turkish_to_ipa(name)
        phonetic_repr = mhelp.map_ipa_to_metaphone(ipa_transcription).upper().replace('B', 'P')
        for gender in genders:
            cursor.execute(
                '''INSERT OR IGNORE INTO names
                   (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives)
                   VALUES (?, ?, ?, ?, ?)''',
                (name, gender, phonetic_repr, ipa_transcription, None),
            )

    conn.commit()
    conn.close()


_CYRILLIC_TO_LATIN = dict(zip(
    'абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
    ['a', 'b', 'v', 'g', 'd', 'e', 'yo', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't',
     'u', 'f', 'kh', 'ts', 'ch', 'sh', 'shch', '', 'y', '', 'e', 'yu', 'ya'],
))

_WIKIDATA_SCRIPTS = {
    'japanese': lambda c: '\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff' or c == '々',
    'chinese': lambda c: '\u4e00' <= c <= '\u9fff' or c in '·-',
    'hindi': lambda c: '\u0900' <= c <= '\u097f',
    'russian': lambda c: '\u0400' <= c <= '\u04ff',
}

_ZH_LABEL_PRIORITY = {'zh-hans': 0, 'zh-cn': 1, 'zh': 2}


def _is_latin_name(text: str) -> bool:
    return bool(text) and all(c.isalpha() and ord(c) < 0x250 or c in "-'" for c in text)


def _in_script(product: str, text: str) -> bool:
    return bool(text) and all(_WIKIDATA_SCRIPTS[product](c) for c in text)


def _cyrillic_to_latin(text: str) -> str:
    return ''.join(_CYRILLIC_TO_LATIN.get(c, c) for c in text.lower())


def _hanzi_to_pinyin(text: str) -> str:
    """约翰 -> Yuēhàn, 迈克尔 -> Màikè'ěr (apostrophe before a/o/e syllables), 玛丽·安 -> Mǎlì Ān."""
    words = []
    for part in filter(None, re.split('[·-]', text)):
        syls = [s[0] for s in pinyin(part, style=Style.TONE)]
        word = syls[0] + ''.join(("'" if unicodedata.normalize('NFD', x)[:1] in ('a', 'o', 'e') else '') + x for x in syls[1:])
        words.append(word.capitalize())
    return ' '.join(words)


def _wikidata_row(product: str, row: dict) -> tuple[str, str | None, NameRepr] | None:
    """Return (display name, original writing, encoding) for one Wikidata given-name row."""
    native = row['native'].strip()
    en = row['en'].strip()
    if product == 'spanish':
        name = native or en
        if not _is_latin_name(name):
            return None
        return name, None, _encode(name, InputType.SPANISH)
    if product == 'russian':
        native = native or row['ru'].strip()
        if not _in_script('russian', native):
            return None
        name = en if _is_latin_name(en) else _cyrillic_to_latin(native).title()
        return name, native, _encode(native, InputType.RUSSIAN)
    if not _in_script(product, native):
        return None
    if product == 'japanese':
        name = en if _is_latin_name(en) else (_japanese_to_romaji(native) or '').title()
        if not _is_latin_name(name):
            return None
        return name, native, _encode(mhelp.strip_accents(name), InputType.JAPANESE)
    if not _is_latin_name(en):
        return None
    if product == 'chinese':
        return _hanzi_to_pinyin(native), native, _encode(en, InputType.ENGLISH)
    return en, native, _encode(en, InputType.ENGLISH)


_SUPPLEMENTARY_CSVS = {
    'chinese': 'datasets/cedict_chinese.csv',
    'spanish': 'datasets/ine_spanish.csv',
    'russian': 'datasets/wiktionary_russian.csv',
}


# INE lists every name held by >= 20 people; rare spellings (Maiquel, Maycol) crowd out equivalents like Miguel.
_INE_MIN_FREQUENCY = 500


def _english_genders(db_file='names_database.db') -> dict[str, str]:
    conn = sqlite3.connect(db_file)
    found = {}
    for name, gender in conn.execute("SELECT name, gender FROM names WHERE gender IN ('boy', 'girl')"):
        found.setdefault(name.lower(), set()).add(gender)
    conn.close()
    return {n: 'unisex' if len(g) > 1 else {'boy': 'male', 'girl': 'female'}[g.pop()] for n, g in found.items()}


def _supplementary_rows(product: str, wikidata_rows: list[dict]) -> list[dict]:
    """Rows from scripts/fetch_extra_names.py, in the Wikidata CSV row shape."""
    path = _SUPPLEMENTARY_CSVS.get(product)
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    out = []
    if product == 'chinese':
        genders = _english_genders()
        genders.update({r['en'].lower(): r['gender'] for r in wikidata_rows if r['en']})
        for r in rows:
            if r['en'].lower() in genders:
                out.append({'qid': '', 'gender': genders[r['en'].lower()], 'native': r['zh'],
                            'native_lang': 'zh-hans', 'ru': '', 'en': r['en']})
    elif product == 'spanish':
        accented = {mhelp.strip_accents(r['native']).lower(): r['native'] for r in wikidata_rows if r['native']}
        for r in rows:
            if int(r['frequency']) < _INE_MIN_FREQUENCY:
                continue
            key = r['name'].lower()
            out.append({'qid': '', 'gender': r['gender'], 'native': accented.get(key, key.title()),
                        'native_lang': 'es', 'ru': '', 'en': ''})
    elif product == 'russian':
        for r in rows:
            out.append({'qid': '', 'gender': r['gender'], 'native': r['name'], 'native_lang': 'ru',
                        'ru': r['name'], 'en': ''})
    return out


def create_wikidata_database(product, csv_file, db_file):
    """Build a name database from a CC0 Wikidata export (scripts/fetch_wikidata_names.py)
    plus the supplementary lists from scripts/fetch_extra_names.py."""
    with open(csv_file, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if product == 'chinese':
        rows.sort(key=lambda r: _ZH_LABEL_PRIORITY.get(r['native_lang'], 3))
        best = {}
        for r in rows:
            best.setdefault((r['qid'], r['gender']), r)
        rows = list(best.values())
    rows.sort(key=lambda r: int(r['qid'][1:]))
    extra = _supplementary_rows(product, rows)
    rows = extra + rows if product == 'chinese' else rows + extra

    if os.path.exists(db_file):
        os.remove(db_file)
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE names (
                        name TEXT,
                        gender TEXT,
                        phonetic_representation TEXT,
                        ipa_transcription TEXT,
                        ipa_alternatives TEXT,
                        original_writing TEXT,
                        PRIMARY KEY (name, gender)
                    )''')
    genders = {'male': ('boy',), 'female': ('girl',), 'unisex': ('boy', 'girl')}
    seen = set()
    for row in tqdm(rows, desc=f"Processing {product} names"):
        parsed = _wikidata_row(product, row)
        if parsed is None:
            continue
        name, original, enc = parsed
        if not (enc.mp or enc.ipa):
            continue
        key = original if product in ('russian', 'chinese') else mhelp.strip_accents(name).lower()
        for gender in genders[row['gender']]:
            if (key, gender) in seen:
                continue
            seen.add((key, gender))
            cursor.execute(
                '''INSERT OR IGNORE INTO names (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives, original_writing)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (name, gender, enc.mp, enc.ipa, '', original),
            )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    csv_file = "datasets/names.csv"
    db_file = "names_database.db"
    if os.path.exists(csv_file):
        create_database(csv_file, db_file)
        print("Database created successfully.")

    arab_csv = "datasets/arabnames.csv"
    arabic_writings_csv = "datasets/arabic_names.csv"
    ar_en_names_csv = "datasets/ar_en_names.csv"
    arab_db = "arabnames_database.db"
    if os.path.exists(arab_csv):
        create_arabic_database(arab_csv, arab_db, arabic_writings_csv=arabic_writings_csv, ar_en_names_csv=ar_en_names_csv)
        print("Arabic database created successfully.")

    korean_csv = "datasets/kpopidolsv3.csv"
    korean_db = "korean_database.db"
    if os.path.exists(korean_csv):
        create_korean_database(korean_csv, korean_db)
        print("Korean database created successfully.")

    turkish_csv = "datasets/turkce_isim.csv"
    turkish_db = "turkish_database.db"
    if os.path.exists(turkish_csv):
        create_turkish_database(turkish_csv, turkish_db)
        print("Turkish database created successfully.")

    for product in ('japanese', 'chinese', 'spanish', 'hindi', 'russian'):
        wikidata_csv = f"datasets/wikidata_{product}.csv"
        if os.path.exists(wikidata_csv):
            create_wikidata_database(product, wikidata_csv, f"{product}_database.db")
            print(f"{product.title()} database created successfully.")
