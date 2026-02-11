import os
import sys
import pytest

os.chdir(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.getcwd())

from api.index import app, get_similar_names, NameRepr


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


class TestFindRedirect:
    def test_redirects_to_pretty_url(self, client):
        response = client.get(
            "/find?name=John&input_type=english&distance_dimension=mp&gender=boy"
        )
        assert response.status_code == 302
        assert "/find/John" in response.headers["Location"]

    def test_redirects_to_index_without_name(self, client):
        response = client.get("/find?name=")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")


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
        assert b"Similar Names to" in response.data
        assert b"John" in response.data


class TestGetSimilarNames:
    def test_returns_ten_results(self):
        results, _ = get_similar_names("John", "english", "mp", "")
        assert len(results) == 10

    def test_result_structure(self):
        results, input_fields = get_similar_names("John", "english", "mp", "")
        name, gender, phonetic_repr, ipa, ipa_alts, score = results[0]
        assert isinstance(name, str)
        assert gender in ("boy", "girl")
        assert isinstance(score, float)

        assert input_fields.name == "John"
        assert isinstance(input_fields.ipa, str)
        assert isinstance(input_fields.mp, str)

    def test_exact_match_ranks_first(self):
        results, _ = get_similar_names("John", "english", "mp", "")
        assert results[0][0] == "John"

    def test_results_sorted_by_score_ascending(self):
        results, _ = get_similar_names("Mary", "english", "mp", "")
        scores = [r[-1] for r in results]
        assert scores == sorted(scores)

    def test_gender_filter_boy(self):
        results, _ = get_similar_names("John", "english", "mp", "boy")
        assert all(r[1] == "boy" for r in results)

    def test_gender_filter_girl(self):
        results, _ = get_similar_names("Mary", "english", "mp", "girl")
        assert all(r[1] == "girl" for r in results)

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


class TestTurkishNameSnapshots:
    def test_cemre_turkish_mp(self):
        results, input_fields = get_similar_names("Cemre", "turkish", "mp", "")
        assert input_fields == NameRepr("Cemre", ipa="d͡ʒemɾe", mp="JMR")
        names = [r[0] for r in results]
        assert names == [
            "Jamar", "Jamir", "Jamari", "Jamarion", "Jeanmarie",
            "Hjalmar", "Hjalmer", "Jamie", "Jayme", "Jamie",
        ]

    def test_mehmet_turkish_mp_boy(self):
        results, input_fields = get_similar_names("Mehmet", "turkish", "mp", "boy")
        assert input_fields == NameRepr("Mehmet", ipa="mehmet", mp="MHMT")
        names = [r[0] for r in results]
        assert names == [
            "Muhammad", "Mohammad", "Mohammed", "Mohamed", "Mamie",
            "May", "Mae", "Mayo", "Moe", "Wm",
        ]

    def test_ayse_turkish_ipa_girl(self):
        results, input_fields = get_similar_names("Ayşe", "turkish", "ipa", "girl")
        assert input_fields == NameRepr("Ayşe", ipa="ajʃe", mp="AS")
        names = [r[0] for r in results]
        assert names == [
            "Anjanette", "Jacey", "Avie", "Anie", "Aisha",
            "Janae", "Jamey", "Jaden", "Jayde", "Jaeda",
        ]
