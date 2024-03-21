from flask import Flask, render_template, request
import sqlite3
from metaphone import doublemetaphone
from nltk import edit_distance
from eng_to_ipa import ipa_list

app = Flask(__name__)

# Function to retrieve top 10 similar names based on phonetic representation
def get_similar_names(input_name, search_type):
    conn = sqlite3.connect('names_database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT * FROM names''')
    all_names = cursor.fetchall()
    similar_names = []

    input_phonetic_repr = doublemetaphone(input_name)[0]
    input_ipa = ipa_list(input_name)[0][0]

    for name, gender, name_phonetic_repr, name_ipa, name_ipa_alts in all_names:
        
        if search_type == 'ipa':
            similarity_score = edit_distance(input_name, name_ipa)
        elif search_type == 'english-mp':
            similarity_score = edit_distance(input_phonetic_repr, name_phonetic_repr)
        elif search_type == 'english-ipa':
            similarity_score = edit_distance(input_ipa, name_ipa)
        elif search_type == 'english-mixedapproach':
            similarity_score = edit_distance(input_ipa, name_phonetic_repr) * 100 + edit_distance(input_phonetic_repr, name_phonetic_repr)
        elif search_type == 'mp':
            similarity_score = edit_distance(input_name.upper(), name_phonetic_repr)

        similar_names.append((name, gender, name_phonetic_repr, name_ipa, name_ipa_alts, similarity_score))

    similar_names.sort(key=lambda x: x[-1])  # Sort by similarity score
    conn.close()
    return similar_names[:10]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/find_similar_names', methods=['POST'])
def find_similar_names():
    input_name = request.form['name']
    search_type = request.form['search_type']  # Added line to retrieve search_type
    similar_names = get_similar_names(input_name, search_type)  # Updated function call
    return render_template('results.html', input_name=input_name, similar_names=similar_names)

if __name__ == '__main__':
    app.run(debug=True)

