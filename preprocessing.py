import csv
import os
import sqlite3
from tqdm import tqdm
from metaphone import doublemetaphone
from eng_to_ipa import ipa_list

from helpers.metaphone_helper import hangul_to_metaphone, hangul_to_phonetic_romanization

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
        phonetic_repr = calculate_phonetic_representation(name)
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


if __name__ == "__main__":
    csv_file = "names.csv"
    db_file = "names_database.db"
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
