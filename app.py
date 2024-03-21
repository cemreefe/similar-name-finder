from flask import Flask, render_template, request
import sqlite3
from metaphone import doublemetaphone
from nltk import edit_distance
from epitran import Epitran
import helpers.metaphone_helper as mhelp
from eng_to_ipa import ipa_list


app = Flask(__name__)

def get_similar_names(input_name, input_type, distance_function, gender):

    # Define separate functions for different cases
    def calculate_similarity_ipa(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
        return edit_distance(input_ipa, name_ipa)

    def calculate_similarity_metaphone(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
        return edit_distance(input_mp, name_phonetic_repr)

    def calculate_similarity_hybrid(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
        return edit_distance(input_mp, name_phonetic_repr) * 100 + edit_distance(input_ipa, name_ipa)

    def calculate_similarity_error(*args):
        return 404

    conn = sqlite3.connect('names_database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT * FROM names''')
    all_names = cursor.fetchall()
    conn.close()

    if input_type == 'english':
        input_mp = doublemetaphone(input_name)[0]
        input_ipa = ipa_list(input_name)[0][0]
    elif input_type == 'ipa':
        input_ipa = input_name
        input_mp = None  # Not needed for IPA input
    elif input_type == 'mp':
        input_ipa = None # Not needed for MP input
        input_mp = input_name  
    elif input_type == 'turkish':
        ep = Epitran('tur-Latn')
        input_ipa = ep.transliterate(input_name)
        input_mp = mhelp.map_ipa_to_metaphone(input_ipa)

    # Determine which function to use based on input type and distance function
    if input_type == 'english' or input_type == 'turkish':
        if distance_function == 'mp':
            calculate_similarity = calculate_similarity_metaphone
        elif distance_function == 'ipa':
            calculate_similarity = calculate_similarity_ipa
        elif distance_function == 'hybrid':
            calculate_similarity = calculate_similarity_hybrid
        else:
            calculate_similarity = calculate_similarity_error
    elif input_type == 'ipa' and distance_function == 'ipa':
        calculate_similarity = calculate_similarity_ipa
    elif input_type == 'mp' and distance_function == 'mp':
        calculate_similarity = calculate_similarity_metaphone
    else:
        calculate_similarity = calculate_similarity_error

    similar_names = []

    for name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts in all_names:
        if gender and name_gender != gender:
            continue  # Skip if gender preference doesn't match

        similarity_score = calculate_similarity(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts)
        similar_names.append((name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts, similarity_score))

    similar_names.sort(key=lambda x: x[-1])  # Sort by similarity score
    return similar_names[:10], (input_name, input_ipa, input_mp)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/find_similar_names', methods=['POST'])
def find_similar_names():
    input_name = request.form['name']
    input_type = request.form['input_type']
    distance_function = request.form['distance_function']
    gender = request.form['gender'] if 'gender' in request.form else None
    similar_names, input_fields = get_similar_names(input_name, input_type, distance_function, gender)
    return render_template('results.html', input_name=input_name, similar_names=similar_names, input_fields=input_fields)

if __name__ == '__main__':
    app.run(debug=True)

