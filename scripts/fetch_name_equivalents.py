"""Build datasets/name_equivalents.csv: English given name -> its form in each destination language.

Sources, in ranking order:
- manual: hand-picked traditional equivalents that Wikidata lacks (John -> Juan).
- label: the target-language labels of Wikidata given-name items labelled with the English name
  (John -> Джон, Michael -> Miguel), CC0. "Said to be the same as" (P460) links were tried and dropped:
  they are too loose (John -> Yann, Jackie).

Usage: python scripts/fetch_name_equivalents.py
"""
import json
import os
import re
import sqlite3
import sys
import unicodedata
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
from fetch_extra_names import _get, _write  # noqa: E402

SPARQL = 'https://query.wikidata.org/sparql'
LANG_PRODUCTS = {'es': 'spanish', 'ru': 'russian', 'zh': 'chinese', 'zh-hans': 'chinese', 'ja': 'japanese', 'hi': 'hindi'}
BATCH = 150

MANUAL = {
    'spanish': {
        'John': 'Juan', 'Jack': 'Juan', 'Joan': 'Juana', 'Jane': 'Juana', 'Michael': 'Miguel', 'Peter': 'Pedro',
        'James': 'Jaime', 'Joseph': 'José', 'William': 'Guillermo', 'Charles': 'Carlos', 'George': 'Jorge',
        'Henry': 'Enrique', 'Thomas': 'Tomás', 'Paul': 'Pablo', 'Mary': 'María', 'Elizabeth': 'Isabel',
        'Anne': 'Ana', 'Ann': 'Ana', 'Catherine': 'Catalina', 'Katherine': 'Catalina', 'Margaret': 'Margarita',
        'Richard': 'Ricardo', 'Stephen': 'Esteban', 'Steven': 'Esteban', 'Anthony': 'Antonio', 'Andrew': 'Andrés',
        'Matthew': 'Mateo', 'Mark': 'Marcos', 'Luke': 'Lucas', 'Francis': 'Francisco', 'Edward': 'Eduardo',
        'Robert': 'Roberto', 'Louis': 'Luis', 'Christopher': 'Cristóbal', 'Susan': 'Susana', 'Helen': 'Elena',
        'Theresa': 'Teresa', 'Teresa': 'Teresa', 'Frederick': 'Federico', 'Alexander': 'Alejandro',
        'Philip': 'Felipe', 'Vincent': 'Vicente', 'Lawrence': 'Lorenzo', 'Albert': 'Alberto', 'Arthur': 'Arturo',
        'Hugh': 'Hugo', 'Julian': 'Julián', 'Martin': 'Martín', 'Simon': 'Simón', 'Timothy': 'Timoteo',
        'Benjamin': 'Benjamín', 'Nicholas': 'Nicolás', 'Patrick': 'Patricio', 'Raymond': 'Ramón', 'Oliver': 'Oliverio',
        'Lucy': 'Lucía', 'Rose': 'Rosa', 'Mariana': 'Mariana', 'Sophia': 'Sofía', 'Sophie': 'Sofía',
        'Isabella': 'Isabel', 'Emily': 'Emilia', 'Charlotte': 'Carlota', 'Caroline': 'Carolina',
        'Josephine': 'Josefina', 'Julia': 'Julia', 'Frances': 'Francisca', 'Agnes': 'Inés', 'Dorothy': 'Dorotea',
        'Eleanor': 'Leonor', 'Beatrice': 'Beatriz', 'Martha': 'Marta', 'Christine': 'Cristina',
        'Christina': 'Cristina', 'Victoria': 'Victoria', 'Veronica': 'Verónica', 'Monica': 'Mónica',
    },
}


def _plain(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text).lower() if c.isalnum())


def _query(names: list[str]) -> list[tuple[str, str, str]]:
    values = ' '.join(json.dumps(n) + '@en' for n in names)
    langs = ', '.join(json.dumps(lang) for lang in LANG_PRODUCTS)
    q = f'''SELECT DISTINCT ?en ?lang ?label WHERE {{
      hint:Query hint:optimizer "None".
      VALUES ?en {{ {values} }}
      ?n rdfs:label ?en.
      ?n wdt:P31 ?cls. VALUES ?cls {{ wd:Q12308941 wd:Q11879590 wd:Q3409032 }}
      ?n rdfs:label ?label.
      BIND(lang(?label) AS ?lang)
      FILTER(?lang IN ({langs}))
    }}'''
    data = json.loads(_get(SPARQL + '?' + urllib.parse.urlencode({'query': q, 'format': 'json'})))
    return [(b['en']['value'], b['lang']['value'], b['label']['value'])
            for b in data['results']['bindings']]


def main() -> None:
    conn = sqlite3.connect('names_database.db')
    names = sorted({n.title() for (n,) in conn.execute("SELECT DISTINCT name FROM names WHERE gender IN ('boy', 'girl')")})
    conn.close()
    rows = [(p, en, native, 'manual') for p, pairs in MANUAL.items() for en, native in pairs.items()]
    for i in range(0, len(names), BATCH):
        for en, lang, label in _query(names[i:i + BATCH]):
            for part in re.split('[/,]', label.split(' (')[0]):
                part = part.strip()
                if part and _plain(part) != _plain(en):
                    rows.append((LANG_PRODUCTS[lang], en, part, 'label'))
        print(f'{min(i + BATCH, len(names))}/{len(names)}', file=sys.stderr)
    order = {'manual': 0, 'label': 1}
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: (r[0], r[1], order[r[3]])):
        if (row[0], row[1], row[2]) not in seen:
            seen.add((row[0], row[1], row[2]))
            out.append(row)
    _write('datasets/name_equivalents.csv', ['product', 'en', 'native', 'source'], out)


if __name__ == '__main__':
    main()
