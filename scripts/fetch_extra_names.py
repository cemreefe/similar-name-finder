"""Download supplementary name lists into datasets/.

- ine_spanish.csv: INE Spain, names held by >= 20 residents (CC BY 4.0, "Fuente: INE").
- nen_russian.csv: NEN names dataset (Moscow ZAGS newborn statistics, curated; CC BY 4.0), restricted to names
  of the Russian tradition (see RUSSIAN_ORIGINS / RUSSIAN_EXTRA / RUSSIAN_EXCLUDED).
- cngender_chinese.csv: given names of mainland Chinese residents with male/female counts, from
  "An Open Dataset of Chinese Name-to-Gender Associations" (Harvard Dataverse, CC0 1.0).
- cedict_chinese.csv: Western given names and their Chinese spelling from CC-CEDICT (CC BY-SA 4.0); shown only as a
  transliteration, never scored as a Chinese name.

Usage: python scripts/fetch_extra_names.py [spanish russian chinese cedict]   (needs xlrd for spanish)
"""
import csv
import gzip
import io
import re
import sys
import time
import urllib.request
from collections import Counter

USER_AGENT = 'namefinder-dataset-builder/1.0 (https://namefinder.dutl.uk; cemreefe@gmail.com)'
INE_URL = 'https://www.ine.es/daco/daco42/nombyapel/nombres_por_edad_media.xls'
NEN_URL = 'https://raw.githubusercontent.com/mdanina/nen-imena-dataset/main/data/names.csv'
CNGENDER_URL = 'https://dataverse.harvard.edu/api/access/datafile/10803450'
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


# NEN's "origin" field: origins of the Russian/Orthodox/European name stock. Names of Arabic, Turkic, Caucasian,
# Central Asian and Mongolian origin (Магомед, Анзор, Азамат, ...) are left out.
RUSSIAN_ORIGINS = {
    'древнегреческое', 'греческое', 'латинское', 'древнеримское', 'славянское', 'древнерусское',
    'греческо-славянское', 'древнееврейское', 'германское', 'скандинавское', 'французское', 'английское',
    'кельтское', 'древнеанглийское', 'польское', 'литературное', 'провансальское', 'древнеарамейское',
}
# Russian names whose NEN origin label is outside RUSSIAN_ORIGINS (or mislabeled, e.g. 'римское').
RUSSIAN_EXTRA = {
    'Дарья', 'Нина', 'Алла', 'Руслан', 'Анжелика', 'Августа', 'Август', 'Берта', 'Матрона', 'Стефанида',
    'Александрина', 'Марика', 'Ярославна', 'Мстислав', 'Марта', 'Савва', 'Фома', 'Абрам', 'Моисей', 'Сарра',
    'Янина', 'Илия', 'Михей', 'Маркел', 'Давыд', 'Лазарь', 'Соломон', 'Рахиль', 'Изабелла', 'Лолита', 'Фрида',
    'Эрвин', 'Гарри',
}
# Tatar, Bashkir, Caucasian and Central Asian names that NEN files under a European origin.
RUSSIAN_EXCLUDED = {
    'Марьям', 'Альфия', 'Хава', 'Фания', 'Аниса', 'Тигран', 'Линар', 'Сослан', 'Инсаф', 'Альфира', 'Рузанна',
    'Сармат', 'Линара', 'Геворг', 'Миран', 'Мариян', 'Амур', 'Исмаил', 'Рим', 'Зайтуна', 'Харис', 'Наида',
    'Ралина', 'Микаил', 'Разина', 'Динис', 'Гаянэ', 'Филюс', 'Галей', 'Севиль', 'Фидания', 'Ринат', 'Радик',
    'Ренат', 'Марсель', 'Румия', 'Сервер', 'Адия', 'Салия', 'Риналь', 'Нино', 'Диас', 'Венер', 'Резеда', 'Анзор',
    'Замира', 'Василя', 'Радис', 'Ильвина', 'Гульниса', 'Дамира', 'Тамила', 'Равиль', 'Самвел', 'Яха', 'Исрапил',
    'Ленар', 'Ленара', 'Мариам', 'Гусен', 'Гумер', 'Апти', 'Ирик', 'Радель', 'Эндже', 'Ранэль', 'Алексан',
    'Ания', 'Эра', 'Дари', 'Анфия', 'Нана', 'Нила', 'Дим', 'Илина', 'Флорида', 'Марс', 'Венера', 'Мариана',
}

# Given names held by fewer people are mostly one-off combinations.
CNGENDER_MIN_COUNT = 500


def fetch_russian() -> None:
    rows = []
    for r in csv.DictReader(io.StringIO(_get(NEN_URL).decode('utf-8-sig'))):
        name = r['name'].strip()
        if name in RUSSIAN_EXCLUDED or (r['origin'] not in RUSSIAN_ORIGINS and name not in RUSSIAN_EXTRA):
            continue
        rows.append((name, {'m': 'male', 'f': 'female'}[r['gender']], r['popularity_bucket'], r['international_forms']))
    _write('datasets/nen_russian.csv', ['name', 'gender', 'popularity', 'international_forms'], rows)


def fetch_chinese_given_names() -> None:
    rows = []
    lines = _get(CNGENDER_URL).decode('utf-8').splitlines()
    for line in lines[1:]:
        name, male, female, _ = line.split('\t')
        male, female = int(float(male or 0)), int(float(female or 0))
        if male + female >= CNGENDER_MIN_COUNT and all('\u4e00' <= c <= '\u9fff' for c in name):
            rows.append((name, male, female))
    rows.sort(key=lambda r: -(r[1] + r[2]))
    _write('datasets/cngender_chinese.csv', ['name', 'male', 'female'], rows)


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
    fetchers = {'spanish': fetch_spanish, 'russian': fetch_russian, 'chinese': fetch_chinese_given_names,
                'cedict': fetch_chinese}
    for product in sys.argv[1:] or fetchers:
        fetchers[product]()
