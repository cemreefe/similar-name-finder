import csv
import os
import sqlite3
from tqdm import tqdm
from metaphone import doublemetaphone
from eng_to_ipa import ipa_list

# Function to calculate phonetic representation using Double Metaphone
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

    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        total_rows = sum(1 for row in reader)
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in tqdm(reader, total=total_rows, desc="Processing CSV"):
            name = row[1]
            gender = row[3]
            phonetic_repr = calculate_phonetic_representation(name)
            ipa_transcription, ipa_alternatives = calculate_ipa_transcription(name)
            try:
                cursor.execute('''INSERT INTO names (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives)
                                VALUES (?, ?, ?, ?, ?)''', (name, gender, phonetic_repr, ipa_transcription, ipa_alternatives))
            except sqlite3.IntegrityError:
                # Skip duplicate names with the same gender
                pass

    conn.commit()
    conn.close()


def create_arabic_database(csv_file, db_file):
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

    with open(csv_file, 'r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
    for row in tqdm(rows, desc="Processing Arabic CSV"):
        name = row['english_name'].strip()
        arabic = row.get('arabic_name', '').strip()
        gender = 'boy' if row.get('gender', 'm').lower() == 'm' else 'girl'
        phonetic_repr = calculate_phonetic_representation(name)
        ipa_transcription, ipa_alternatives = calculate_ipa_transcription(name)
        try:
            cursor.execute('''INSERT INTO names (name, gender, phonetic_representation, ipa_transcription, ipa_alternatives, original_writing)
                            VALUES (?, ?, ?, ?, ?, ?)''', (name, gender, phonetic_repr, ipa_transcription, ipa_alternatives, arabic or None))
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


if __name__ == "__main__":
    csv_file = "names.csv"
    db_file = "names_database.db"
    create_database(csv_file, db_file)
    print("Database created successfully.")

    arab_csv = "datasets/arabic_names.csv"
    arab_db = "arabnames_database.db"
    if os.path.exists(arab_csv):
        create_arabic_database(arab_csv, arab_db)
        print("Arabic database created successfully.")
