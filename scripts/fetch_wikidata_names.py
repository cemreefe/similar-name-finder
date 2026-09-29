"""Download given names from Wikidata (CC0) into datasets/wikidata_<product>.csv.

Usage: python scripts/fetch_wikidata_names.py [japanese chinese spanish hindi russian]
"""
import csv
import json
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = 'https://query.wikidata.org/sparql'
USER_AGENT = 'namefinder-dataset-builder/1.0 (https://namefinder.dutl.uk; cemreefe@gmail.com)'
GENDER_TYPES = 'VALUES ?t { wd:Q12308941 wd:Q11879590 wd:Q3409032 }'

QUERIES = {
    'japanese': f'''
SELECT ?n ?t ?native ?en WHERE {{
  {GENDER_TYPES}
  ?n wdt:P31 ?t ; wdt:P407 wd:Q5287 ; wdt:P1705 ?native .
  FILTER(LANG(?native) = "ja")
  OPTIONAL {{ ?n rdfs:label ?en FILTER(LANG(?en) = "en") }}
}}''',
    'chinese': f'''
SELECT ?n ?t ?native ?en WHERE {{
  {GENDER_TYPES}
  ?n wdt:P31 ?t ; rdfs:label ?native ; rdfs:label ?en .
  FILTER(LANG(?native) = "zh-hans" || LANG(?native) = "zh-cn" || LANG(?native) = "zh")
  FILTER(LANG(?en) = "en")
}}''',
    'hindi': f'''
SELECT ?n ?t ?native ?en WHERE {{
  {GENDER_TYPES}
  ?n wdt:P31 ?t ; rdfs:label ?native ; rdfs:label ?en .
  FILTER(LANG(?native) = "hi")
  FILTER(LANG(?en) = "en")
}}''',
    'spanish': f'''
SELECT ?n ?t ?native ?en WHERE {{
  {GENDER_TYPES}
  ?n wdt:P31 ?t ; wdt:P407 wd:Q1321 .
  OPTIONAL {{ ?n rdfs:label ?native FILTER(LANG(?native) = "es") }}
  OPTIONAL {{ ?n rdfs:label ?en FILTER(LANG(?en) = "en") }}
}}''',
    'russian': f'''
SELECT ?n ?t ?native ?ru ?en WHERE {{
  {GENDER_TYPES}
  ?n wdt:P31 ?t .
  {{ ?n wdt:P282 wd:Q8209 }} UNION {{ ?n wdt:P407 wd:Q7737 }}
  OPTIONAL {{ ?n wdt:P1705 ?native FILTER(LANG(?native) = "ru") }}
  OPTIONAL {{ ?n rdfs:label ?ru FILTER(LANG(?ru) = "ru") }}
  OPTIONAL {{ ?n rdfs:label ?en FILTER(LANG(?en) = "en") }}
}}''',
}

TYPE_TO_GENDER = {
    'Q12308941': 'male',
    'Q11879590': 'female',
    'Q3409032': 'unisex',
}


def run_query(query: str) -> list[dict]:
    url = ENDPOINT + '?format=json&query=' + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                bindings = json.load(resp)['results']['bindings']
            rows = []
            for b in bindings:
                row = {k: v['value'] for k, v in b.items()}
                row['native_lang'] = b.get('native', {}).get('xml:lang', '')
                rows.append(row)
            return rows
        except Exception as exc:
            print(f'  attempt {attempt + 1} failed: {exc}', file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError('Wikidata query failed repeatedly')


def fetch(product: str) -> None:
    rows = run_query(QUERIES[product])
    out = f'datasets/wikidata_{product}.csv'
    fields = ['qid', 'gender', 'native', 'native_lang', 'ru', 'en']
    seen = set()
    with open(out, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            record = {
                'qid': r['n'].rsplit('/', 1)[-1],
                'gender': TYPE_TO_GENDER[r['t'].rsplit('/', 1)[-1]],
                'native': r.get('native', ''),
                'native_lang': r['native_lang'],
                'ru': r.get('ru', ''),
                'en': r.get('en', ''),
            }
            key = tuple(record.values())
            if key in seen:
                continue
            seen.add(key)
            writer.writerow(record)
    print(f'{product}: {len(seen)} rows -> {out}')


if __name__ == '__main__':
    for product in sys.argv[1:] or QUERIES:
        fetch(product)
