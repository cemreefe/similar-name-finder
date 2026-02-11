from dataclasses import dataclass
from enum import Enum
from typing import assert_never
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
import unicodedata


class InputType(Enum):
    ENGLISH = 'english'
    TURKISH = 'turkish'
    IPA = 'ipa'
    MP = 'mp'


class DistanceDimension(Enum):
    IPA = 'ipa'
    MP = 'mp'
    SPELLING = 'spelling'


@dataclass
class NameRepr:
    name: str
    ipa: str | None = None
    mp: str | None = None


def _distance(x, y):
    return 1 - jaro_winkler_similarity(x, y)


def _encode(name, input_type: InputType) -> NameRepr:
    match input_type:
        case InputType.ENGLISH:
            normalized = name.capitalize()
            return NameRepr(name, ipa=ipa_list(normalized)[0][0], mp=doublemetaphone(normalized)[0].upper())
        case InputType.TURKISH:
            ep = Epitran('tur-Latn')
            ipa = ep.transliterate(name)
            mp = mhelp.map_ipa_to_metaphone(ipa).upper().replace('B', 'P')
            return NameRepr(name, ipa=ipa, mp=mp)
        case InputType.IPA:
            return NameRepr(name, ipa=name)
        case InputType.MP:
            return NameRepr(name, mp=name.upper())
        case _ as unreachable:
            assert_never(unreachable)


def _phonetic_score(primary_input, primary_db, secondary_input, secondary_db):
    score = _distance(primary_input, primary_db)
    if secondary_input and secondary_db:
        score += _distance(secondary_input, secondary_db) / 100
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


def _score(encoded, dim, name, name_mp, name_ipa):
    match dim:
        case DistanceDimension.IPA:
            return _phonetic_score(encoded.ipa, name_ipa, encoded.mp, name_mp)
        case DistanceDimension.MP:
            return _phonetic_score(encoded.mp, name_mp, encoded.ipa, name_ipa)
        case DistanceDimension.SPELLING:
            return _spelling_score(encoded.name, name)
        case _ as unreachable:
            assert_never(unreachable)


def get_similar_names(input_name, input_type, distance_dimension, gender):
    encoded = _encode(input_name, InputType(input_type))
    dim = DistanceDimension(distance_dimension)

    if dim is DistanceDimension.IPA and encoded.ipa is None:
        raise ValueError(f"Cannot use IPA distance with {input_type!r} input")
    if dim is DistanceDimension.MP and encoded.mp is None:
        raise ValueError(f"Cannot use metaphone distance with {input_type!r} input")

    conn = sqlite3.connect('names_database.db')
    cursor = conn.cursor()
    if gender:
        cursor.execute('SELECT * FROM names WHERE gender = ?', (gender,))
    else:
        cursor.execute('SELECT * FROM names')
    all_names = cursor.fetchall()
    conn.close()

    similar_names = []
    for name, name_gender, name_mp, name_ipa, name_ipa_alts in all_names:
        score = _score(encoded, dim, name, name_mp, name_ipa)
        similar_names.append((name, name_gender, name_mp, name_ipa, name_ipa_alts, score))

    similar_names.sort(key=lambda x: x[-1])
    return similar_names[:10], encoded


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
