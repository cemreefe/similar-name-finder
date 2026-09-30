"""Download supplementary name lists into datasets/.

- ine_spanish.csv: INE Spain, names held by >= 20 residents (CC BY 4.0, "Fuente: INE").
- wiktionary_russian.csv: ru.wiktionary "* мужские/женские имена/ru" categories (CC BY-SA 4.0).
- cedict_chinese.csv: Western given names and their Chinese spelling from CC-CEDICT (CC BY-SA 4.0).

Usage: python scripts/fetch_extra_names.py [spanish russian chinese]   (needs xlrd for spanish)
"""
import csv
import gzip
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

USER_AGENT = 'namefinder-dataset-builder/1.0 (https://namefinder.dutl.uk; cemreefe@gmail.com)'
INE_URL = 'https://www.ine.es/daco/daco42/nombyapel/nombres_por_edad_media.xls'
WIKTIONARY_API = 'https://ru.wiktionary.org/w/api.php'
CEDICT_URL = 'https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz'


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except OSError:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))


def _write(path: str, header: list[str], rows) -> None:
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(path, len(rows))


def fetch_spanish() -> None:
    import xlrd
    book = xlrd.open_workbook(file_contents=_get(INE_URL))
    rows = []
    for sheet, gender in (('Hombres', 'male'), ('Mujeres', 'female')):
        s = book.sheet_by_name(sheet)
        for i in range(s.nrows):
            order, name, freq, _ = s.row_values(i)[:4]
            if isinstance(freq, float) and str(order).isdigit():
                rows.append((name.strip(), gender, int(freq)))
    _write('datasets/ine_spanish.csv', ['name', 'gender', 'frequency'], rows)


def _category_members(title: str) -> list[str]:
    names, cont = [], {}
    while True:
        params = {'action': 'query', 'list': 'categorymembers', 'cmtitle': title, 'cmlimit': '500',
                  'cmnamespace': '0', 'format': 'json', **cont}
        data = json.loads(_get(WIKTIONARY_API + '?' + urllib.parse.urlencode(params)))
        names += [m['title'] for m in data['query']['categorymembers']]
        if 'continue' not in data:
            return names
        cont = {'cmcontinue': data['continue']['cmcontinue']}
        time.sleep(0.2)


def _name_categories(word: str) -> list[str]:
    params = {'action': 'query', 'list': 'search', 'srnamespace': '14', 'srlimit': '500',
              'srsearch': f'intitle:"{word} имена/ru"', 'format': 'json'}
    data = json.loads(_get(WIKTIONARY_API + '?' + urllib.parse.urlencode(params)))
    return sorted(m['title'] for m in data['query']['search'] if m['title'].lower().endswith(f'{word} имена/ru'))


def fetch_russian() -> None:
    rows = []
    for word, gender in (('мужские', 'male'), ('женские', 'female')):
        names = set()
        for title in _name_categories(word):
            names.update(_category_members(title))
        rows += [(n, gender) for n in sorted(names)]
    _write('datasets/wiktionary_russian.csv', ['name', 'gender'], rows)


_NAME_ENTRY = re.compile(r'^\S+ (\S+) \[[^]]+\] /(?:\(name\) )?([A-Z][a-z]+)(?: \((?:name|given name|male given name|female given name)\))?/')
_PERSON_ENTRY = re.compile(r'^\S+ (\S+) \[[^]]+\] /([A-Z][a-z]+)(?: [A-Z]\.)* [A-Z][\w\'-]+.*?\(\d')


def fetch_chinese() -> None:
    text = gzip.GzipFile(fileobj=io.BytesIO(_get(CEDICT_URL))).read().decode('utf-8')
    direct, preferred, persons = {}, {}, Counter()
    for line in text.splitlines():
        if line.startswith('#'):
            continue
        m = _NAME_ENTRY.match(line)
        if m and '(name)' in line and '·' not in m.group(1):
            direct.setdefault(m.group(2), m.group(1))
            continue
        m = _PERSON_ENTRY.match(line)
        if m and '·' in m.group(1):
            persons[(m.group(2), m.group(1).split('·')[0])] += 1
    for (en, zh), count in persons.most_common():
        if count >= 2 and en not in preferred:
            preferred[en] = zh
    for (en, zh), _ in persons.most_common():
        direct.setdefault(en, zh)
    direct.update(preferred)
    _write('datasets/cedict_chinese.csv', ['en', 'zh'], sorted(direct.items()))


if __name__ == '__main__':
    fetchers = {'spanish': fetch_spanish, 'russian': fetch_russian, 'chinese': fetch_chinese}
    for product in sys.argv[1:] or fetchers:
        fetchers[product]()
