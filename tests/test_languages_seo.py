import re
from urllib.parse import quote

import pytest

from api.index import resolve_auto_input_types, app, get_similar_names, _detect_input_script, _ARAB_DB_PATH
from api.translations import LANGUAGES, TRANSLATIONS, ARABIC_PAGE_TRANSLATIONS, KOREAN_PAGE_TRANSLATIONS


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


NEW_INPUTS = [
    ("José", "spanish"),
    ("João", "portuguese"),
    ("Jürgen", "german"),
    ("Giuseppe", "italian"),
    ("Дмитрий", "russian"),
    ("Dmitriy", "russian"),
    ("محمد", "arabic"),
    ("प्रिया", "hindi"),
]


@pytest.mark.parametrize("name,input_type", NEW_INPUTS)
def test_new_input_types_encode_and_return_results(name, input_type):
    results, encoded = get_similar_names(name, input_type, "sound", "")
    assert len(results) == 10
    assert encoded.ipa
    assert encoded.mp


@pytest.mark.parametrize("name,input_type,expected", [
    ("José", "spanish", "Jose"),
    ("Juan", "spanish", "Juan"),
    ("Jorge", "spanish", "George"),
    ("Наталья", "russian", "Natalie"),
])
def test_new_input_types_find_expected_english_names(name, input_type, expected):
    results, _ = get_similar_names(name, input_type, "sound", "")
    assert expected.lower() in [r[0].lower() for r in results]


@pytest.mark.parametrize("name,expected", [("محمد", "muhammad"), ("فاطمة", "fatima")])
def test_arabic_script_matches_arabic_database(name, expected):
    results, _ = get_similar_names(name, "arabic", "sound", "", db_path=_ARAB_DB_PATH)
    assert expected in [r[0].lower() for r in results[:3]]


@pytest.mark.parametrize("text,script", [
    ("Дмитрий", "russian"), ("محمد", "arabic"), ("प्रिया", "hindi"), ("John", None),
])
def test_detect_new_scripts(text, script):
    assert _detect_input_script(text) == script


def test_script_mismatch_suggests_russian(client):
    html = client.get("/find/" + quote("Дмитрий") + "?input_type=english").get_data(as_text=True)
    assert "input_type=russian" in html


@pytest.mark.parametrize("lang", ["de", "it", "ru", "ar", "id", "vi"])
def test_new_ui_languages_are_complete(lang):
    assert lang in LANGUAGES
    assert set(TRANSLATIONS["en"]) <= set(TRANSLATIONS[lang])
    assert set(ARABIC_PAGE_TRANSLATIONS["en"]) - set(ARABIC_PAGE_TRANSLATIONS[lang]) <= set(TRANSLATIONS["en"])
    assert lang in KOREAN_PAGE_TRANSLATIONS


@pytest.mark.parametrize("path", ["/", "/my-name-in-arabic/", "/my-name-in-korean/"])
@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_every_page_renders_in_every_language(client, path, lang):
    response = client.get(f"{path}?lang={lang}")
    assert response.status_code == 200


def test_arabic_ui_is_rtl(client):
    html = client.get("/?lang=ar").get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in html


def test_new_input_options_rendered(client):
    html = client.get("/").get_data(as_text=True)
    for value in ("spanish", "portuguese", "german", "italian", "russian", "arabic", "hindi"):
        assert f'<option value="{value}"' in html


def test_default_input_is_auto(client):
    html = client.get("/?lang=de").get_data(as_text=True)
    assert '<option value="auto" selected' in html


@pytest.mark.parametrize("name,hint,expected", [
    ("Дмитрий", None, ["russian"]),
    ("محمد", None, ["arabic"]),
    ("민준", None, ["korean"]),
    ("Ayşe", None, ["turkish"]),
    ("Muñoz", None, ["spanish"]),
    ("João", None, ["portuguese"]),
    ("Günter", "turkish", ["turkish", "german"]),
    ("Mehmet", "turkish", ["turkish", "english"]),
    ("Mehmet", None, ["english"]),
    ("Mehmet", "korean", ["english"]),
])
def test_resolve_auto_input_types(name, hint, expected):
    assert resolve_auto_input_types(name, hint) == expected


def test_auto_uses_script_without_mismatch_notice(client):
    html = client.get("/find/%D0%94%D0%BC%D0%B8%D1%82%D1%80%D0%B8%D0%B9").get_data(as_text=True)
    assert "script-mismatch" not in html
    assert "Searched as Russian" in html
    auto, _ = get_similar_names("Дмитрий", "auto", "sound", "")
    explicit, _ = get_similar_names("Дмитрий", "russian", "sound", "")
    assert [r[0] for r in auto] == [r[0] for r in explicit]


def test_auto_arabic_script_on_arabic_page(client):
    html = client.get("/my-name-in-arabic/find/%D9%85%D8%AD%D9%85%D8%AF").get_data(as_text=True)
    assert "muhammad" in html.lower()


def test_auto_merges_hint_and_english():
    results, _ = get_similar_names("Mehmet", "auto", "sound", "", hint="turkish")
    turkish, _ = get_similar_names("Mehmet", "turkish", "sound", "")
    assert results[0][5] <= turkish[0][5]


def test_hint_forwarded_by_redirect_and_not_canonical(client):
    response = client.get("/find?name=Mehmet&hint=turkish")
    assert response.headers["Location"] == "/find/Mehmet?hint=turkish"
    html = client.get("/find/Mehmet?hint=turkish").get_data(as_text=True)
    assert '<link rel="canonical" href="https://namefinder.dutl.uk/find/Mehmet">' in html
    assert "Searched as Turkish + English" in html


def test_invalid_query_params_do_not_crash(client):
    response = client.get("/find/John?input_type=bogus&distance_dimension=bogus")
    assert response.status_code == 200


def test_robots_txt(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "Sitemap: https://namefinder.dutl.uk/sitemap.xml" in response.get_data(as_text=True)


def test_sitemap_xml(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    body = response.get_data(as_text=True)
    locs = re.findall(r"<loc>(.*?)</loc>", body)
    assert len(locs) == len(set(locs))
    assert "https://namefinder.dutl.uk/" in locs
    assert "https://namefinder.dutl.uk/my-name-in-korean/find/John" in locs
    assert "https://namefinder.dutl.uk/my-name-in-arabic/?lang=de" in locs
    assert all(loc.startswith("https://namefinder.dutl.uk/") for loc in locs)
    assert len(locs) < 50000


def test_canonical_drops_filters_and_defaults(client):
    html = client.get("/find/John?input_type=english&distance_dimension=spelling&gender=male").get_data(as_text=True)
    assert '<link rel="canonical" href="https://namefinder.dutl.uk/find/John">' in html
    assert '<meta name="robots" content="noindex, follow">' in html


def test_canonical_keeps_language(client):
    html = client.get("/find/Mehmet?lang=tr").get_data(as_text=True)
    assert '<link rel="canonical" href="https://namefinder.dutl.uk/find/Mehmet?lang=tr">' in html
    assert 'name="robots"' not in html


def test_results_page_has_summary_and_popular_links(client):
    html = client.get("/find/John").get_data(as_text=True)
    assert 'class="results-summary"' in html
    assert 'class="popular-searches"' in html
    assert 'href="/find/Mehmet?input_type=turkish"' in html


def test_structured_data_is_valid_json(client):
    import json
    html = client.get("/my-name-in-korean/?lang=ko").get_data(as_text=True)
    raw = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    data = json.loads(raw)
    assert data["@type"] == "WebApplication"
    assert data["url"] == "https://namefinder.dutl.uk/my-name-in-korean/"
    assert data["inLanguage"] == "ko"


def test_cache_headers(client):
    response = client.get("/find/John")
    assert "s-maxage" in response.headers["Cache-Control"]
