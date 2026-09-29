# Turkish names dataset

`turkce_isim.csv` is the source for the Turkish Name Finder. It is the
unchanged `turkce_isim.csv` file from Niyazi Kemer's
[Turkish Names / Türkçe İsimler](https://www.kaggle.com/datasets/nikemr/14111-turkish-names-with-gender-identifiers)
dataset (version 6, downloaded 2026-09-13). Kaggle declares the dataset
available under the MIT License.

The file contains a `name` column and a `sex` column:

- `E` — male
- `K` — female
- `U` — unisex

The importer removes exact duplicate rows and stores each unisex name for both
gender filters. Its SHA-256 is
`384fb051a5b1a60ba4c9a3534fc1f4d04dac19cdb985970be423be7295ac0271`.
