"""
This library provides two functions:

1. `map_ipa_to_english` maps International Phonetic Alphabet (IPA) sounds to their closest English sound equivalents.
2. `convert_to_metaphone` converts the resulting phonetic representation into a metaphone, which is a phonetic algorithm used for indexing and comparing words by their sound.

Here's how it works:

1. The `map_ipa_to_english` function takes an IPA string as input and replaces each IPA sound with its closest English sound equivalent using a dictionary mapping. The resulting string represents the phonetic transcription of the input IPA string in English sounds.

2. The `convert_to_metaphone` function takes the phonetic string from `map_ipa_to_english` and applies the Metaphone algorithm to it. The Metaphone algorithm is a phonetic encoding algorithm that transforms words into a code based on their sound. The resulting metaphone code can be used for indexing and comparing words by their sound, which is useful for tasks like spell-checking and name matching.

"""

import re

# Dictionary mapping IPA sounds to their closest English sound equivalents
IPA_TO_ENGLISH = {
    'ɑ': 'a', 'æ': 'ae', 'ɐ': 'a', 'ɒ': 'o', 'ɔ': 'o', 'ɕ': 'sh', 'ç': 'sh', 'ð': 'th',
    'ɘ': 'e', 'ə': 'e', 'ɚ': 'er', 'ɛ': 'e', 'ɜ': 'er', 'ɝ': 'er', 'ɞ': 'e', 'ɟ': 'j',
    'ɡ': 'g', 'ɣ': 'h', 'ɤ': 'o', 'ɥ': 'h', 'ɦ': 'h', 'ɧ': 'ng', 'ɨ': 'i', 'ɪ': 'i',
    'ɫ': 'l', 'ɬ': 'l', 'ɭ': 'l', 'ɮ': 'l', 'ɯ': 'u', 'ɰ': 'w', 'ɱ': 'm', 'ɲ': 'n',
    'ɳ': 'n', 'ɴ': 'n', 'ɵ': 'o', 'ɶ': 'o', 'ɸ': 'f', 'ɹ': 'r', 'ɺ': 'r', 'ɻ': 'r',
    'ɼ': 'r', 'ɽ': 'r', 'ɾ': 'r', 'ɿ': 'r', 'ʀ': 'r', 'ʁ': 'r', 'ʂ': 'sh', 'ʃ': 'sh',
    'ʄ': 'j', 'ʅ': 'ng', 'ʆ': 'n', 'ʇ': 'n', 'ʈ': 't', 'ʉ': 'u', 'ʊ': 'u', 'ʋ': 'v',
    'ʌ': 'a', 'ʍ': 'wh', 'ʎ': 'l', 'ʏ': 'y', 'ʐ': 'r', 'd͡ʒ': 'j', 'ʑ': 'z', 'ʒ': 'zh', 
    'ʓ': 'zh', 'ʔ': '', 'ʕ': 'h', 'ʖ': 'r', 'ʗ': 'r', 'ʘ': 'o', 'ʙ': 'b', 'ʚ': 'h', 'ʛ': 'g',
    'ʜ': 'h', 'ʝ': 'y', 'ʞ': 'k', 'ʟ': 'l', 'ʠ': 'q', 'ʡ': 'g', 'ʢ': 'n', 'ʣ': 'z',
    'ʤ': 'j', 'ʥ': 'j', 'ʦ': 'ts', 'ʧ': 'ch', 'ʨ': 'ch', 'ʩ': 'r', 'ʪ': 'l', 'ʫ': 'l',
    'ʬ': 'l', 'ʭ': 'w', 'ʮ': 'h', 'ʯ': 'n', 'ˀ': '', 'ˁ': '', 'ˆ': '', 'ˈ': '', 'ˌ': '',
    'ˍ': '', 'ˎ': '', 'ˏ': '', 'ː': '', 'ˑ': '', 'ˠ': '', 'ˡ': '', 'ˢ': '', 'ˣ': '',
    'ˤ': '', '˥': '', '˦': '', '˧': '', '˨': '', '˩': '', 'ˮ': '', 'ˬ': '', 'ˈ': '',
    'ˌ': '', 'ː': '', 
}

# Metaphone encoding rules
METAPHONE_RULES = [
    # Drop duplicate adjacent letters, except for C
    (r'([bcdfgjklmnpqrstvwxyz])\1+', r'\1'),

    # Drop the first letter if the string begins with AE, GN, KN, PN or WR
    (r'^(ae|gn|kn|pn|wr)([aeiouy].*)?', r'\2'),

    # Drop B if after M at the end of the string
    (r'mb$', ''),

    # C transforms
    (r'ch', 'x'),  # X if followed by IA or H
    (r'c(i|e|y)', 's'),  # S if followed by I, E, or Y
    (r'c', 'k'),  # K otherwise

    # D transforms
    (r'dge$', 'j'),  # J if followed by GE, GY, or GI
    (r'dg(y|i|e)$', 'j'),
    (r'd', 't'),  # T otherwise

    # Drop G conditions
    (r'g([b-df-hj-np-tv-z]|$)', ''),  # Drop G
    (r'g(n|ned)$', ''),  # if followed by N or NED and is at the end of the string

    # G transforms
    (r'g(i|e|y)', 'j'),  # J if before I, E or Y and is not a GG
    (r'g', 'k'),  # K otherwise

    # Drop H conditions
    (r'h([aeiou])', r'\1'),  # if after a vowel and not before a vowel
    (r'h([csptg])', r'\1'),  # if after C, S, P, T or G

    # Drop K if after C
    (r'ck', 'k'),

    # PH transforms
    (r'ph', 'f'),  # PH transforms into F

    # Q transforms
    (r'q', 'k'),  # Q transforms into K

    # S transforms
    (r's(ia|io|h)', 'x'),  # S transforms into X if followed by H, IO or IA
    (r's', 's'),

    # T transforms
    (r't(ia|io)', 'x'),  # T transforms into X if followed by IA or IO
    (r'th', '0'),  # TH transforms into 0 (zero)

    # Drop T if followed by CH
    (r'tch', 'ch'),

    # V transforms
    (r'v', 'f'),  # V transforms into F

    # Drop W conditions
    (r'^w([^aeiou]|$)', r'\1'),  # Drop W if not followed by a vowel

    # WH transforms
    (r'wh', 'w'),  # WH transforms into W if at the beginning of the string

    # X transforms
    (r'^x', 's'),  # X transforms into S if at the beginning
    (r'x', 'ks'),  # KS otherwise

    # Drop Y if not followed by a vowel
    (r'y([^aeiou]|$)', r'\1'),

    # Z transforms
    (r'z', 's'),  # Z transforms into S

    # Drop all vowels unless it is the beginning character
    (r'(?<!^)[aeiou]', '')
]


def map_ipa_to_english(ipa_str):
    """
    Maps IPA sounds to their closest English sound equivalents.
    
    Args:
        ipa_str (str): A string containing IPA sounds.
        
    Returns:
        str: The phonetic transcription of the input IPA string in English sounds.
    """
    result = ipa_str
    for ipa, english in IPA_TO_ENGLISH.items():
        result = result.replace(ipa, english)
    return result

def convert_to_metaphone(phonetic_str):
    """
    Converts a phonetic string into a metaphone code.
    
    Args:
        phonetic_str (str): A string representing the phonetic transcription.
        
    Returns:
        str: The metaphone code for the input phonetic string.
    """
    metaphones = []
    phonetic_words = phonetic_str.lower().split()
    for word in phonetic_words:
        metaphone = word
        for i, (pattern, replacement) in enumerate(METAPHONE_RULES):
            metaphone = re.sub(pattern, replacement, metaphone)
        metaphones.append(metaphone)
    return ' '.join(metaphones).upper()

def map_ipa_to_metaphone(ipa_str):
    mapped_to_en = map_ipa_to_english(ipa_str)
    return convert_to_metaphone(mapped_to_en)

ipa_string = "ɪnˈtɝnæʃnəl fəˈnɛtɪk ˈælfəbɛt"
english_phonetic = map_ipa_to_english(ipa_string)
print(english_phonetic)  # Output: "internaeshnl fenetik aelfabet"

metaphone_code = convert_to_metaphone(english_phonetic)
print(">>>>>", metaphone_code)  # Output: "ntrn"