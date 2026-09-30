# Supplementary name lists

These lists fill gaps in the Wikidata exports (see `WIKIDATA_NAMES.md`). Regenerate with
`python scripts/fetch_extra_names.py` (the Spanish list needs `pip install xlrd`), then rebuild the
databases with `python preprocessing.py`. Downloaded 2026-09-30.

| File | Source | Licence | Used for |
| --- | --- | --- | --- |
| `cedict_chinese.csv` | [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict): entries marked "(name)" plus the most common first-name spelling in "First·Last" person entries | CC BY-SA 4.0 | Standard Chinese spellings of Western names (John → 约翰, David → 大卫). Only names that exist in the English list are used; gender comes from Wikidata when it has the name, otherwise from the English list. Results show Hanzi + Pinyin, not the English name. |
| `ine_spanish.csv` | [INE, Estadística de nombres](https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&menu=resultados&secc=1254736195498&idp=1254734710990) (`nombres_por_edad_media.xls`): names of residents of Spain held by at least 20 people | CC BY 4.0 — Fuente: Instituto Nacional de Estadística | Spanish finder. Single-word names with frequency >= 500; accents are restored from Wikidata where known. |
| `wiktionary_russian.csv` | [Russian Wiktionary](https://ru.wiktionary.org/) categories ending in "мужские имена/ru" / "женские имена/ru" | CC BY-SA 4.0 | Russian finder: Cyrillic names, including Russian spellings of foreign names (Джон, Эмма). |

Because CC-CEDICT and Wiktionary are CC BY-SA 4.0, `chinese_database.db`, `russian_database.db`
and the two CSVs derived from them are shared under CC BY-SA 4.0 as well.
