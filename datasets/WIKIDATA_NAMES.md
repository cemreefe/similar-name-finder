# Wikidata given-name datasets

`wikidata_japanese.csv`, `wikidata_spanish.csv` and `wikidata_hindi.csv` are exports of Wikidata given-name items (instances of male given name
Q12308941, female given name Q11879590 or unisex given name Q3409032). Wikidata data is released
under CC0 1.0, so no attribution is required; the source is noted here for provenance.

Regenerate with `python scripts/fetch_wikidata_names.py`, then build `<product>_database.db`
with `python preprocessing.py`. Exported 2026-09-29.

| File | Selection | Native writing |
| --- | --- | --- |
| japanese | language of name = Japanese (P407 Q5287) | native label (P1705, ja) |
| hindi | any given name with a hi label | Hindi label (Devanagari only) |
| spanish | language of name = Spanish (P407 Q1321) | – (Spanish label) |

Columns: `qid, gender (male/female/unisex), native, native_lang, ru, en`. Unisex names are stored
for both gender filters. Rows whose native writing is not in the expected script, or whose
romanized name is not Latin, are skipped by `preprocessing.create_wikidata_database`.

Chinese and Russian are no longer built from Wikidata: any given name with a Chinese or Cyrillic label let in foreign
names (Jalmari → 雅尔马里) and regional ones. See `EXTRA_NAMES.md`.
