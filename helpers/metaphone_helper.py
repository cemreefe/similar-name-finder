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
    'tɕʰ': 'ch', 'tɕ': 'ch', 'ʰ': '', '̯': '', 'ɹ̩': '', '̩': '', 'ŋ': 'ng',
    'x': 'h',
    'j': 'y',
    'ɑ': 'a', 'æ': 'ae', 'ɐ': 'a', 'ɒ': 'o', 'ɔ': 'o', 'ɕ': 'sh', 'ç': 'sh', 'ð': 'th',
    'ɘ': 'e', 'ə': 'e', 'ɚ': 'er', 'ɛ': 'e', 'ɜ': 'er', 'ɝ': 'er', 'ɞ': 'e', 'ɟ': 'j',
    'ɑ̃': 'a', 'ɛ̃': 'e', 'ɔ̃': 'o', 'œ̃': 'e',
    'ɡ': 'gu', 'ɣ': 'h', 'ɤ': 'o', 'ɥ': 'h', 'ɦ': 'h', 'ɧ': 'ng', 'ɨ': 'i', 'ɪ': 'i',
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
    (r'(?<!^)[aeiou]', ''),

    # Replace vowels with A
    (r'[aeiouy]', r'a'),
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


def turkish_to_ipa(text: str) -> str:
    """Turkish orthography to IPA."""
    text = text.lower().strip()
    result = []
    soft_vowels = 'eiöü'
    for i, c in enumerate(text):
        next_soft = i + 1 < len(text) and text[i + 1].lower() in soft_vowels
        match c:
            case 'ç':
                result.append('tʃ')
            case 'ş':
                result.append('ʃ')
            case 'ğ':
                pass
            case 'ı':
                result.append('ɯ')
            case 'ö':
                result.append('œ')
            case 'ü':
                result.append('y')
            case 'c':
                result.append('d͡ʒ')
            case 'g':
                result.append('ɟ' if next_soft else 'ɡ')
            case 'j':
                result.append('ʒ')
            case 'y':
                result.append('j')
            case 'r':
                result.append('ɾ')
            case _:
                result.append(c)
    return ''.join(result)


def french_to_ipa(text: str) -> str:
    """French orthography to IPA."""
    text = text.lower().strip()
    result = []
    soft_vowels = 'éèêëeiïîy'
    i = 0
    while i < len(text):
        c = text[i]
        next_c = text[i + 1] if i + 1 < len(text) else ''
        next2 = text[i + 2] if i + 2 < len(text) else ''
        next_soft = next_c in soft_vowels
        if i + 3 <= len(text) and text[i:i+3] == 'eau':
            result.append('o')
            i += 3
            continue
        if i + 3 <= len(text) and text[i:i+3] == 'oin':
            result.append('wɛ')
            i += 3
            continue
        if i + 2 <= len(text):
            two = text[i:i+2]
            if two == 'ch':
                result.append('ʃ')
                i += 2
                continue
            if two == 'qu':
                result.append('k')
                i += 2
                continue
            if two == 'ph':
                result.append('f')
                i += 2
                continue
            if two == 'ou':
                result.append('u')
                i += 2
                continue
            if two == 'ai' and next2 == 'l' and (i + 3 >= len(text) or text[i+3] in ' e'):
                result.append('aj')
                i += 3
                continue
            if two == 'ai' or two == 'ay':
                result.append('ɛ')
                i += 2
                continue
            if two == 'ei':
                result.append('ɛ')
                i += 2
                continue
            if two == 'oi':
                result.append('wa')
                i += 2
                continue
            if two == 'au':
                result.append('o')
                i += 2
                continue
            if two == 'eu':
                result.append('œ')
                i += 2
                continue
            if two == 'œu':
                result.append('œ')
                i += 2
                continue
            if two == 'ui':
                result.append('wi')
                i += 2
                continue
            if two == 'gn':
                result.append('ɲ')
                i += 2
                continue
            if two == 'il' and (i + 2 >= len(text) or text[i+2] in ' e'):
                result.append('j')
                i += 2
                continue
        match c:
            case 'ç':
                result.append('s')
            case 'à' | 'â' | 'ä':
                result.append('ɑ')
            case 'é' | 'è' | 'ê' | 'ë':
                result.append('e')
            case 'î' | 'ï':
                result.append('i')
            case 'ô' | 'ö':
                result.append('o')
            case 'ù' | 'û' | 'ü':
                result.append('y')
            case 'œ':
                result.append('œ')
            case 'æ':
                result.append('ɛ')
            case 'c':
                result.append('s' if next_soft else 'k')
            case 'g':
                result.append('ʒ' if next_soft else 'ɡ')
            case 'j':
                result.append('ʒ')
            case 'r':
                result.append('ʁ')
            case 'x':
                result.append('ks')
            case 'h':
                pass
            case _:
                if c.isalpha():
                    result.append(c)
        i += 1
    return _french_nasalize(''.join(result))


def _french_nasalize(ipa: str) -> str:
    """Replace vowel+n/m with nasal vowel (ɑ̃, ɛ̃, ɔ̃, œ̃) where n/m is not followed by vowel."""
    out = []
    i = 0
    while i < len(ipa):
        c = ipa[i]
        nc = ipa[i + 1] if i + 1 < len(ipa) else ''
        nnc = ipa[i + 2] if i + 2 < len(ipa) else ''
        has_nasal_consonant = nc in ('n', 'm')
        is_nasal_end = nnc == '' or nnc not in 'aeiouɑɛɔœ'
        if c in 'aɑ' and has_nasal_consonant and is_nasal_end:
            out.append('ɑ̃')
            i += 2
        elif c in 'eɛ' and has_nasal_consonant and is_nasal_end:
            out.append('ɛ̃')
            i += 2
        elif c == 'o' and has_nasal_consonant and is_nasal_end:
            out.append('ɔ̃')
            i += 2
        elif c in 'iyœ' and has_nasal_consonant and is_nasal_end:
            out.append('œ̃')
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)

# ipa_string = "ɪnˈtɝnæʃnəl fəˈnɛtɪk ˈælfəbɛt"
# english_phonetic = map_ipa_to_english(ipa_string)
# print(english_phonetic)  # Output: "internaeshnl fenetik aelfabet"

# metaphone_code = convert_to_metaphone(english_phonetic)
# print(">>>>>", metaphone_code)  # Output: "ntrn"