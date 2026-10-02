# Supplementary name lists

These lists are the Chinese and Russian name lists and fill gaps in the Spanish Wikidata export (see `WIKIDATA_NAMES.md`). Regenerate with
`python scripts/fetch_extra_names.py` (the Spanish list needs `pip install xlrd`), then rebuild the
databases with `python preprocessing.py`. Downloaded 2026-09-30.

| File | Source | Licence | Used for |
| --- | --- | --- | --- |
| `cngender_chinese.csv` | [An Open Dataset of Chinese Name-to-Gender Associations](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/UAARYY) (Harvard Dataverse, `CnGender.txt`; [GitHub](https://github.com/tongt1213/Chinese-Gender-dataset)): given names of Chinese residents with male/female counts | CC0 1.0 | Chinese finder. Given names held by >= 500 people (about 8,000). Shown as tone-marked Pinyin + Hanzi and matched by their Pinyin sound; gender is male/female when >= 80% of holders are, otherwise both. |
| `nen_russian.csv` | [NEN names dataset](https://github.com/mdanina/nen-imena-dataset) (popularity from open Moscow ZAGS newborn statistics, curated by the NEN editorial team) | CC BY 4.0 — © NEN, https://github.com/mdanina/nen-imena-dataset | Russian finder. Only names of the Russian / Orthodox / European name stock (about 580): Arabic, Turkic, Caucasian, Central Asian and Mongolian names are left out; see `RUSSIAN_ORIGINS`, `RUSSIAN_EXTRA` and `RUSSIAN_EXCLUDED` in `scripts/fetch_extra_names.py`. Its `international_forms` (Иван: John; Jean; Juan) rank Иван first for John. |
| `cedict_chinese.csv` | [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict): entries marked "(name)" plus the most common first-name spelling in "First·Last" person entries | CC BY-SA 4.0 | Chinese spellings of Western names (John → 约翰). If the spelling is itself a Chinese given name (大卫), it ranks first; otherwise it is only shown as a transliteration (see below). |
| `ine_spanish.csv` | [INE, Estadística de nombres](https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&menu=resultados&secc=1254736195498&idp=1254734710990) (`nombres_por_edad_media.xls`): names of residents of Spain held by at least 20 people | CC BY 4.0 — Fuente: Instituto Nacional de Estadística | Spanish finder. Single-word names with frequency >= 500; accents are restored from Wikidata where known. |

`datasets/transliterations.csv` (and the transliteration boxes built from it) derives from CC-CEDICT and is shared under
CC BY-SA 4.0. The name databases themselves contain no CC-CEDICT data.

## Transliterations

Spellings of English names in Chinese, Russian or Japanese script (John → 约翰 / Джон / ジョン) that are not names of
that language are kept out of the scored results. `preprocessing.create_transliterations` collects them from CC-CEDICT
and the Wikidata `label` rows of `name_equivalents.csv` into `datasets/transliterations.csv`; a finder shows them in a
separate "Transliteration, not a native name" box only when the input is exactly the English name or the spelling.

## English → local name equivalents

`datasets/name_equivalents.csv` (built by `python scripts/fetch_name_equivalents.py`) maps each English name in
`names_database.db` to its form in the destination languages, so "Michael" on the Spanish finder shows Miguel before
the (also real, INE-listed) spelling Michael. Two sources:

- `manual`: a short hand-picked list of traditional Spanish equivalents (John → Juan, Peter → Pedro, …) that Wikidata
  labels don't give.
- `label`: target-language labels of Wikidata given-name items whose English label is the name (John → Джон,
  Michael → Miguel/Майкл), CC0. "Said to be the same as" (P460) links were too loose (John → Yann, Jackie) and are not used.

On the Chinese finder CC-CEDICT, and on the Russian finder NEN's international forms, are top-tier equivalents. They
only affect names that are in the destination list. At query time, results matching a
`manual`/CC-CEDICT equivalent rank first, then `label` equivalents, then an exact spelling match, then phonetic score.
