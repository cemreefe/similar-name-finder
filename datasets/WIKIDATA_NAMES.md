# Wikidata given-name datasets

`wikidata_japanese.csv`, `wikidata_chinese.csv`, `wikidata_spanish.csv`, `wikidata_hindi.csv` and
`wikidata_russian.csv` are exports of Wikidata given-name items (instances of male given name
Q12308941, female given name Q11879590 or unisex given name Q3409032). Wikidata data is released
under CC0 1.0, so no attribution is required; the source is noted here for provenance.

Regenerate with `python scripts/fetch_wikidata_names.py`, then build `<product>_database.db`
with `python preprocessing.py`. Exported 2026-09-29.

| File | Selection | Native writing |
| --- | --- | --- |
| japanese | language of name = Japanese (P407 Q5287) | native label (P1705, ja) |
| chinese | any given name with a zh / zh-hans / zh-cn label | Chinese label (zh-hans preferred) |
| hindi | any given name with a hi label | Hindi label (Devanagari only) |
| spanish | language of name = Spanish (P407 Q1321) | – (Spanish label) |
| russian | writing system Cyrillic (P282 Q8209) or language Russian (P407 Q7737) | native label or ru label |

Columns: `qid, gender (male/female/unisex), native, native_lang, ru, en`. Unisex names are stored
for both gender filters. Rows whose native writing is not in the expected script, or whose
romanized name is not Latin, are skipped by `preprocessing.create_wikidata_database`.
