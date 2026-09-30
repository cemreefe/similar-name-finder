# Similar Names Finder

Currently lives on [namefinder.dutl.uk/](https://namefinder.dutl.uk/)

This Flask web application helps users find similar names based on phonetic similarity. It utilizes various algorithms to calculate the similarity between names, allowing users to search for similar names in different languages or using different phonetic representations.

## Features

- **Phonetic Similarity:** Users can input a name and choose between different phonetic representations (e.g., English, IPA, Metaphone) to find similar names.
- **Language Support:** Input names in English, Turkish, Spanish, Portuguese, German, Italian, French, Filipino, Russian (Cyrillic), Arabic script, Hindi (Devanagari), Chinese, Korean (Hangul), and Japanese — each is transliterated to IPA/Metaphone for comparison. The interface is available in 16 languages.
- **Turkish Name Finder:** Search more than 13,000 Turkish given names while preserving Turkish characters and filtering by gender. The data source and licence are documented in [`datasets/TURKISH_NAMES.md`](datasets/TURKISH_NAMES.md).
- **Japanese, Chinese, Spanish, Hindi and Russian Name Finders:** `/my-name-in-<language>/` searches given names from Wikidata (CC0) and shows each match in its native script. Chinese, Spanish and Russian are supplemented with CC-CEDICT, INE Spain and Russian Wiktionary. See [`datasets/WIKIDATA_NAMES.md`](datasets/WIKIDATA_NAMES.md) and [`datasets/EXTRA_NAMES.md`](datasets/EXTRA_NAMES.md) for sources and licences.
- **Customizable Search:** Users can specify the desired phonetic representation and gender for the similar names they want to find.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/cemreefe/similar-names-finder.git
   ```

2. Navigate to the project directory:

   ```bash
   cd similar-names-finder
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Build the name databases (including the Turkish database):

   ```bash
   python preprocessing.py
   ```

5. Run the Flask application:

   ```bash
   python -m api.index
   ```

6. Open your web browser and go to `http://localhost:5000` to access the application.

## Usage

1. Enter a name in the input field on the homepage.
2. Choose the input type (e.g. English, Turkish, Spanish, Russian, Arabic, Hindi, IPA, Metaphone).
3. Select the distance function input (Metaphone, IPA).
4. Optionally, specify the gender for more tailored results.
5. Click on the "Find Similar Names" button.
6. View the results showing similar names based on the selected criteria.

The Turkish name finder is available at `/my-name-in-turkish/`.

## Acknowledgments

- [Flask](https://flask.palletsprojects.com/) - Web framework used in the project.
- [Metaphone](https://pypi.org/project/Metaphone/) - Library for phonetic encoding.
- [NLTK](https://www.nltk.org/) - Library for natural language processing tasks.
- [EngToIPA](https://github.com/mphilli/eng_to_ipa) - Library for converting English text to IPA phonetic transcription.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request with your suggestions, bug fixes, or enhancements.
