from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from metaphone import doublemetaphone
from epitran import Epitran
import helpers.metaphone_helper as mhelp
from eng_to_ipa import ipa_list
from jellyfish import jaro_winkler_similarity
import os
from urllib.parse import unquote
import re


def distance_function(x, y):
    return 1 - jaro_winkler_similarity(x, y)


def _similarity_ipa(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
    if input_mp and name_phonetic_repr:
        return distance_function(input_ipa, name_ipa) + distance_function(input_mp, name_phonetic_repr)/100
    return distance_function(input_ipa, name_ipa)


def _similarity_metaphone(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
    if input_ipa and name_ipa:
        return distance_function(input_mp, name_phonetic_repr) + distance_function(input_ipa, name_ipa)/100
    return distance_function(input_mp, name_phonetic_repr)


def _similarity_spelling(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts):
    _input_name = re.sub(r'(.)\1+', r'\1', input_name)
    _name = re.sub(r'(.)\1+', r'\1', name)
    return distance_function(_input_name, _name)


def _similarity_error(*args):
    return 404


app = Flask(__name__)


def get_similar_names(input_name, input_type, distance_dimension, gender):
    conn = sqlite3.connect('names_database.db')
    cursor = conn.cursor()
    if gender:
        cursor.execute('SELECT * FROM names WHERE gender = ?', (gender,))
    else:
        cursor.execute('SELECT * FROM names')
    all_names = cursor.fetchall()
    conn.close()

    if input_type == 'english':
        input_mp = doublemetaphone(input_name)[0].upper()
        input_ipa = ipa_list(input_name)[0][0]
    elif input_type == 'ipa':
        input_ipa = input_name
        input_mp = None
    elif input_type == 'mp':
        input_ipa = None
        input_mp = input_name.upper()
    elif input_type == 'turkish':
        ep = Epitran('tur-Latn')
        input_ipa = ep.transliterate(input_name)
        input_mp = mhelp.map_ipa_to_metaphone(input_ipa).upper()
        input_mp = input_mp.replace('B', 'P')
    else:
        raise ValueError(f"Unknown input_type: {input_type!r}")

    if input_type in ('english', 'turkish'):
        similarity_funcs = {
            'mp': _similarity_metaphone,
            'ipa': _similarity_ipa,
            'spelling': _similarity_spelling,
        }
        calculate_similarity = similarity_funcs.get(distance_dimension, _similarity_error)
    elif input_type == 'ipa' and distance_dimension == 'ipa':
        calculate_similarity = _similarity_ipa
    elif input_type == 'mp' and distance_dimension == 'mp':
        calculate_similarity = _similarity_metaphone
    else:
        calculate_similarity = _similarity_error

    similar_names = []
    for name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts in all_names:
        similarity_score = calculate_similarity(input_name, input_ipa, input_mp, name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts)
        similar_names.append((name, name_gender, name_phonetic_repr, name_ipa, name_ipa_alts, similarity_score))

    similar_names.sort(key=lambda x: x[-1])
    return similar_names[:10], (input_name, input_ipa, input_mp)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/find', methods=['GET'])
def find_redirect():
    input_name = request.args.get('name')
    input_name = unquote(input_name)
    if not input_name:
        return redirect(url_for('index'))
    return redirect(url_for(
        'find_similar_names_pretty', input_name=input_name,
        input_type=request.args.get('input_type'),
        distance_dimension=request.args.get('distance_dimension'),
        gender=request.args.get('gender')
    ))


@app.route('/find/<string:input_name>', methods=['GET'])
def find_similar_names_pretty(input_name):
    input_name = unquote(input_name)
    input_type = request.args.get('input_type')
    distance_dimension = request.args.get('distance_dimension')
    gender = request.args.get('gender')

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
