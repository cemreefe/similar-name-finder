from flask import Flask, render_template, request
import sqlite3
from metaphone import doublemetaphone
from nltk import edit_distance

app = Flask(__name__)

# Function to retrieve top 10 similar names based on phonetic representation
def get_similar_names(input_name):
    conn = sqlite3.connect('names_database.db')
    cursor = conn.cursor()
    input_phonetic_repr = doublemetaphone(input_name)[0]
    cursor.execute('''SELECT name FROM names''')
    all_names = cursor.fetchall()
    similar_names = []

    for name in all_names:
        name_phonetic_repr = doublemetaphone(name[0])[0]
        similarity_score = edit_distance(input_phonetic_repr, name_phonetic_repr)
        similar_names.append((name[0], name_phonetic_repr, similarity_score))

    similar_names.sort(key=lambda x: x[1])  # Sort by similarity score
    conn.close()
    return similar_names[:10]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/find_similar_names', methods=['POST'])
def find_similar_names():
    input_name = request.form['name']
    similar_names = get_similar_names(input_name)
    return render_template('results.html', input_name=input_name, similar_names=similar_names)

if __name__ == '__main__':
    app.run(debug=True)

