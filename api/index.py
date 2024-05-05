from flask import Flask, render_template, request
import sqlite3
from metaphone import doublemetaphone
from nltk import edit_distance
from epitran import Epitran
import helpers.metaphone_helper as mhelp
from eng_to_ipa import ipa_list
from jellyfish import jaro_winkler_similarity
import os

# distance_function = edit_distance
distance_function = lambda x, y: 1 - jaro_winkler_similarity(x, y)

app = Flask(__name__)

def get_similar_names(input_name, input_type, distance_dimension, gender):

    # Define separate functions for different cases
    def calculate_similarity_ipa(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
        if input_mp and name_phonetic_repr:
            return distance_function(input_ipa, name_ipa) + distance_function(input_mp, name_phonetic_repr)/100
        return distance_function(input_ipa, name_ipa)

    def calculate_similarity_metaphone(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
        if input_ipa and name_ipa:
            return distance_function(input_mp, name_phonetic_repr) + distance_function(input_ipa, name_ipa)/100
        return distance_function(input_mp, name_phonetic_repr)

    def calculate_similarity_error(*args):
        return 404

    conn = sqlite3.connect('names_database.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT * FROM names''')
    all_names = cursor.fetchall()
    conn.close()

    if input_type == 'english':
        input_mp = doublemetaphone(input_name)[0].upper()
        input_ipa = ipa_list(input_name)[0][0]
    elif input_type == 'ipa':
        input_ipa = input_name
        input_mp = None  # Not needed for IPA input
    elif input_type == 'mp':
        input_ipa = None # Not needed for MP input
        input_mp = input_name.upper()
    elif input_type == 'turkish':
        ep = Epitran('tur-Latn')
        input_ipa = ep.transliterate(input_name)
        input_mp = mhelp.map_ipa_to_metaphone(input_ipa).upper()

    # Determine which function to use based on input type and distance function
    if input_type == 'english' or input_type == 'turkish':
        if distance_dimension == 'mp':
            calculate_similarity = calculate_similarity_metaphone
        elif distance_dimension == 'ipa':
            calculate_similarity = calculate_similarity_ipa
        else:
            calculate_similarity = calculate_similarity_error
    elif input_type == 'ipa' and distance_dimension == 'ipa':
        calculate_similarity = calculate_similarity_ipa
    elif input_type == 'mp' and distance_dimension == 'mp':
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

@app.route('/find', methods=['POST'])
def find_similar_names():
    input_type = request.form['input_type']
    input_name = request.form['name'].capitalize() if not input_type == 'mp' else request.form['name'].upper()
    distance_dimension = request.form['distance_dimension']
    gender = request.form['gender'] if 'gender' in request.form else None
    similar_names, input_fields = get_similar_names(input_name, input_type, distance_dimension, gender)
    return render_template(
        'index.html', 
        input_name=input_name, 
        input_type=input_type, 
        input_fields=input_fields, 
        similar_names=similar_names, 
        distance_dimension=distance_dimension,
        gender=gender
    )

if __name__ == '__main__':
    if os.environ.get('VERCEL', None):
        app.run(debug=False, host="0.0.0.0", port=8443)
    else:
        app.run(debug=True)

