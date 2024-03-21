import csv
import sqlite3
from nltk import edit_distance
from metaphone import doublemetaphone

# Function to calculate phonetic representation using Double Metaphone
def calculate_phonetic_representation(name):
    return doublemetaphone(name)[0]

# Function to create the SQLite database and populate it with name-gender-phonetic pairs
def create_database(csv_file, db_file):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS names (
                        name TEXT,
                        gender TEXT,
                        phonetic_representation TEXT,
                        PRIMARY KEY (name, gender)
                    )''')

    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header
        for row in reader:
            name = row[1]
            gender = row[3]
            phonetic_repr = calculate_phonetic_representation(name)
            try:
                cursor.execute('''INSERT INTO names (name, gender, phonetic_representation)
                                VALUES (?, ?, ?)''', (name, gender, phonetic_repr))
            except sqlite3.IntegrityError:
                # Skip duplicate names with the same gender
                pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    csv_file = "names.csv"
    db_file = "names_database.db"
    create_database(csv_file, db_file)
    print("Database created successfully.")
