import os
import sys
import pytest

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.getcwd())

from api.index import app, get_similar_names, _ARAB_DB_PATH, _repr_order, DistanceDimension
import helpers.metaphone_helper as mhelp


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestIndexRoute:
    def test_index_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"Similar Names Finder" in response.data


class TestUiLanguages:
    def test_language_picker_includes_new_languages(self, client):
        response = client.get("/")
        assert response.status_code == 200

        html = response.data.decode("utf-8")
        assert "हिन्दी" in html
        assert "Español" in html
        assert "Português (Brasil)" in html

        assert 'hreflang="hi"' in html
        assert 'hreflang="es"' in html
        assert 'hreflang="pt-BR"' in html


class TestFindRedirect:
    def test_redirects_to_pretty_url(self, client):
        response = client.get(
            "/find?name=John&input_type=english&distance_dimension=mp&gender=male"
        )
        assert response.status_code == 302
        assert "/find/John" in response.headers["Location"]

    def test_redirects_to_index_without_name(self, client):
        response = client.get("/find?name=")
        assert response.status_code == 302
        assert "/" in response.headers["Location"] and "find" not in response.headers["Location"]

    def test_pt_br_lang_preserved_and_defaults_stripped(self, client):
        response = client.get("/find?name=John&lang=pt-BR&input_type=english&distance_dimension=sound&gender=")
        assert response.status_code == 302
        assert response.headers["Location"] == "/find/John?lang=pt-BR"


class TestSemiPhonetic:
    def test_ipa_to_semiphonetic_strips_stress_marks(self):
        assert mhelp.ipa_to_semiphonetic("ˈɛlə") == "ELE"

    def test_ipa_to_semiphonetic_turkish_ayse(self):
        assert mhelp.ipa_to_semiphonetic("ajʃe") == "AYXE"

    def test_repr_order_env_override(self, monkeypatch):
        monkeypatch.setenv("NAMEF_REPR_ORDER", "mp,semi")
        assert _repr_order() == [DistanceDimension.MP, DistanceDimension.SEMI]


class TestFindRoute:
    def test_find_returns_200(self, client):
        response = client.get(
            "/find/John?input_type=english&distance_dimension=mp&gender="
        )
        assert response.status_code == 200

    def test_find_renders_results(self, client):
        response = client.get(
            "/find/John?input_type=english&distance_dimension=mp&gender="
        )
        assert b"Similar to" in response.data
        assert b"John" in response.data

    def test_script_mismatch_shows_disclaimer(self, client):
        response = client.get("/find/%E8%8A%B3?input_type=english&distance_dimension=sound&gender=")
        assert response.status_code == 200
        assert b"Switch to" in response.data
        assert b"Chinese" in response.data
        assert b"Japanese" in response.data
        assert b"script-mismatch" in response.data


class TestGetSimilarNames:
    def test_returns_ten_results(self):
        results, _ = get_similar_names("John", "english", "mp", "")
        assert len(results) == 10

    def test_result_structure(self):
        results, input_fields = get_similar_names("John", "english", "mp", "")
        name, gender, phonetic_repr, ipa, ipa_alts, score, original_writing = results[0]
        assert isinstance(name, str)
        assert gender in ("male", "female")
        assert isinstance(score, float)

        assert input_fields.name == "John"
        assert isinstance(input_fields.ipa, str)
        assert isinstance(input_fields.mp, str)

    def test_exact_match_ranks_first(self):
        results, _ = get_similar_names("John", "english", "mp", "")
        assert results[0][0] == "John"

    def test_results_sorted_by_score_ascending(self):
        results, _ = get_similar_names("Mary", "english", "mp", "")
        scores = [r[5] for r in results]
        assert scores == sorted(scores)

    def test_gender_filter_male(self):
        results, _ = get_similar_names("John", "english", "mp", "male")
        assert all(r[1] == "male" for r in results)

    def test_gender_filter_female(self):
        results, _ = get_similar_names("Mary", "english", "mp", "female")
        assert all(r[1] == "female" for r in results)

    def test_no_gender_filter_returns_mixed(self):
        results, _ = get_similar_names("Sam", "english", "mp", "")
        genders = {r[1] for r in results}
        assert len(genders) > 1

    def test_ipa_distance_dimension(self):
        results, _ = get_similar_names("John", "english", "ipa", "")
        assert len(results) == 10
        assert results[0][0] == "John"

    def test_spelling_distance_dimension(self):
        results, _ = get_similar_names("John", "english", "spelling", "")
        assert len(results) == 10
        assert results[0][0] == "John"

    def test_mp_input_type(self):
        results, input_fields = get_similar_names("JN", "mp", "mp", "")
        assert len(results) == 10
        assert input_fields.mp == "JN"

    def test_ipa_input_type(self):
        results, input_fields = get_similar_names("dʒɑn", "ipa", "ipa", "")
        assert len(results) == 10
        assert input_fields.ipa == "dʒɑn"

    def test_french_input_type(self):
        results, input_fields = get_similar_names("Jean", "french", "sound", "")
        assert len(results) == 10
        assert input_fields.ipa is not None
        assert input_fields.mp is not None

    def test_chinese_romanized_input(self):
        results, input_fields = get_similar_names("Wei", "chinese", "sound", "")
        assert len(results) == 10
        assert input_fields.ipa == "wei̯"
        assert input_fields.mp == "W"

    def test_chinese_pinyin_xiao(self):
        results, input_fields = get_similar_names("Xiao", "chinese", "sound", "")
        assert input_fields.ipa == "ɕjau̯"
        assert input_fields.mp == "SA"
        names = [r[0] for r in results]
        assert "Zoe" in names or "Zoey" in names

    def test_chinese_character_fang(self):
        results, input_fields = get_similar_names("芳", "chinese", "sound", "")
        assert input_fields.ipa == "faŋ"
        assert input_fields.mp == "FN"
        names = [r[0] for r in results]
        assert "Fawn" in names or "Fanny" in names

    def test_korean_hangul_input(self):
        results, input_fields = get_similar_names("김", "korean", "sound", "")
        assert input_fields.ipa is not None
        assert input_fields.mp is not None
        assert len(results) == 10

    def test_japanese_kanji_input(self):
        results, input_fields = get_similar_names("田中", "japanese", "sound", "")
        assert input_fields.ipa == "tɑˈnɑkə"
        assert input_fields.mp == "TNK"
        assert len(results) == 10


class TestMetaphoneOutput:
    """MP must only contain plain ASCII capital letters A-Z, digit 0, and space."""
    _VALID_MP_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0 ')

    @pytest.mark.parametrize('name,input_type', [
        ('cemre', 'english'), ('cemre', 'turkish'), ('cemre', 'french'),
        ('Jean', 'french'), ('Marie', 'french'), ('François', 'french'),
        ('Ayşe', 'turkish'), ('Mehmet', 'turkish'), ('Cemre', 'turkish'),
        ('John', 'english'), ('Mary', 'english'), ('Wei', 'chinese'),
        ('四川', 'chinese'), ('김民', 'korean'), ('田中', 'japanese'), ('Maria', 'filipino'),
    ])
    def test_mp_only_plain_capitals(self, name, input_type):
        results, input_fields = get_similar_names(name, input_type, 'sound', '')
        assert input_fields.mp is not None
        for c in input_fields.mp:
            assert c in self._VALID_MP_CHARS, f'MP {repr(input_fields.mp)} has invalid char {repr(c)} for {name}/{input_type}'


class TestEncodingConsistentAcrossDatabases:
    """Input encoding must not change depending on which DB is queried."""

    @pytest.mark.parametrize('name,input_type', [
        ('cemre', 'turkish'),
        ('Ayşe', 'turkish'),
        ('Jean', 'french'),
        ('John', 'english'),
        ('Wei', 'chinese'),
    ])
    def test_input_fields_same_for_english_and_arabic_db(self, name, input_type):
        _, fields_en = get_similar_names(name, input_type, 'sound', '')
        _, fields_ar = get_similar_names(name, input_type, 'sound', '', db_path=_ARAB_DB_PATH)
        assert fields_en.mp == fields_ar.mp, (
            f"MP differs across DBs for {name}/{input_type}: "
            f"english={fields_en.mp}, arabic={fields_ar.mp}"
        )
        assert fields_en.ipa == fields_ar.ipa, (
            f"IPA differs across DBs for {name}/{input_type}: "
            f"english={fields_en.ipa}, arabic={fields_ar.ipa}"
        )


class TestTurkishNameSnapshots:
    def test_cemre_turkish_mp(self):
        results, input_fields = get_similar_names("Cemre", "turkish", "mp", "")
        assert input_fields.name == "Cemre"
        assert input_fields.ipa == "d͡ʒemɾe"
        assert input_fields.mp == "JMR"
        assert input_fields.semi == "JEMRE"
        names = [r[0] for r in results]
        assert names == [
            "Jimmie", "Jamie", "Jimmy", "Jami", "Jim",
            "Jaime", "Jermaine", "James", "Jeffrey", "Geoffrey",
        ]

    def test_mehmet_turkish_mp_male(self):
        results, input_fields = get_similar_names("Mehmet", "turkish", "mp", "male")
        assert input_fields.name == "Mehmet"
        assert input_fields.ipa == "mehmet"
        assert input_fields.mp == "MHMT"
        assert input_fields.semi == "MEHMET"
        names = [r[0] for r in results]
        assert names == [
            "Mamie", "Mae", "May", "Marty", "Myrtle",
            "Martin", "Milton", "Millard", "Meredith", "Margaret",
        ]

    def test_ayse_turkish_ipa_female(self):
        results, input_fields = get_similar_names("Ayşe", "turkish", "ipa", "female")
        assert input_fields.name == "Ayşe"
        assert input_fields.ipa == "ajʃe"
        assert input_fields.mp == "AS"
        assert input_fields.semi == "AYXE"
        names = [r[0] for r in results]
        assert names == [
            "Asia", "Alisha", "Marsha", "Marcia", "Jaylen",
            "Jaiden", "Elsa", "Arthur", "Martha", "Jazmine",
        ]
