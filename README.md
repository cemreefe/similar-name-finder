# Similar Names Finder

This Flask web application helps users find similar names based on phonetic similarity. It utilizes various algorithms to calculate the similarity between names, allowing users to search for similar names in different languages or using different phonetic representations.

## Features

- **Phonetic Similarity:** Users can input a name and choose between different phonetic representations (e.g., English, IPA, Metaphone) to find similar names.
- **Language Support:** Supports English and Turkish names, with the ability to transliterate Turkish names to IPA for comparison.
- **Customizable Search:** Users can specify the desired phonetic representation and gender for the similar names they want to find.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/your_username/similar-names-finder.git
   ```

2. Navigate to the project directory:

   ```bash
   cd similar-names-finder
   ```

3. Install the required dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the Flask application:

   ```bash
   python app.py
   ```

5. Open your web browser and go to `http://localhost:5000` to access the application.

## Usage

1. Enter a name in the input field on the homepage.
2. Choose the input type (English, IPA, Metaphone, Turkish).
3. Select the distance function input (Metaphone, IPA).
4. Optionally, specify the gender for more tailored results.
5. Click on the "Find Similar Names" button.
6. View the results showing similar names based on the selected criteria.

## Acknowledgments

- [Flask](https://flask.palletsprojects.com/) - Web framework used in the project.
- [Metaphone](https://pypi.org/project/Metaphone/) - Library for phonetic encoding.
- [Epitran](https://pypi.org/project/epitran/) - Library for transliterating text to IPA.
- [NLTK](https://www.nltk.org/) - Library for natural language processing tasks.
- [EngToIPA](https://github.com/mphilli/eng_to_ipa) - Library for converting English text to IPA phonetic transcription.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request with your suggestions, bug fixes, or enhancements.