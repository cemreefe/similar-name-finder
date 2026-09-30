import re
import sqlite3
from urllib.parse import quote

import pytest

from api.index import resolve_auto_input_types, app, get_similar_names, _detect_input_script, _ARAB_DB_PATH, _TURKISH_DB_PATH, _WORLD_DB_PATHS
from preprocessing import _hanzi_to_pinyin
from api.translations import (
    LANGUAGES, TRANSLATIONS, ARABIC_PAGE_TRANSLATIONS, KOREAN_PAGE_TRANSLATIONS, TURKISH_PAGE_TRANSLATIONS,
    WORLD_LANGUAGE_NAMES, WORLD_PAGE_TEMPLATES, WORLD_PRODUCTS, get_world_page_translations,
)


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


@pytest.mark.parametrize("path", ["/", "/my-name-in-arabic/", "/my-name-in-turkish/", "/my-name-in-korean/"])
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


@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_turkish_page_is_translated(lang):
    assert set(TURKISH_PAGE_TRANSLATIONS[lang]) == set(TURKISH_PAGE_TRANSLATIONS["en"])
    assert TRANSLATIONS[lang]["ad_banner_turkish_title"]


def test_turkish_finder_auto_detects_and_is_indexed(client):
    html = client.get("/my-name-in-turkish/find/Ay%C5%9Fe").get_data(as_text=True)
    assert "Ayşe" in html
    assert '<option value="auto" selected' in html
    assert 'href="https://namefinder.dutl.uk/my-name-in-turkish/find/Ay%C5%9Fe"' in html
    assert "noindex" not in html


def test_english_name_finds_turkish_names():
    results, _ = get_similar_names("Jennifer", "auto", "sound", "", db_path=_TURKISH_DB_PATH)
    assert len(results) == 10


def test_turkish_finder_in_sitemap(client):
    locs = re.findall(r"<loc>(.*?)</loc>", client.get("/sitemap.xml").get_data(as_text=True))
    assert "https://namefinder.dutl.uk/my-name-in-turkish/find/John" in locs
    assert "https://namefinder.dutl.uk/find/Ay%C5%9Fe" in locs


WORLD_EXPECTATIONS = [
    ("japanese", "Emma", "えま"),
    ("chinese", "Michael", "迈克"),
    ("spanish", "Michael", "Miguel"),
    ("hindi", "Rahul", "राहुल"),
    ("russian", "Дмитрий", "Дмитрий"),
    ("chinese", "John", "约翰"),
    ("chinese", "David", "大卫"),
    ("russian", "Emma", "Эмма"),
    ("russian", "Джон", "Джон"),
    ("spanish", "Lucia", "Lucía"),
]


@pytest.mark.parametrize("product,minimum", [("chinese", 10000), ("spanish", 3000), ("russian", 20000)])
def test_supplemented_world_databases_are_large(product, minimum):
    conn = sqlite3.connect(_WORLD_DB_PATHS[product])
    assert conn.execute("SELECT COUNT(*) FROM names").fetchone()[0] >= minimum
    conn.close()


@pytest.mark.parametrize("hanzi,expected", [("约翰", "Yuēhàn"), ("迈克尔", "Màikè'ěr"), ("玛丽·安", "Mǎlì Ān")])
def test_hanzi_to_pinyin(hanzi, expected):
    assert _hanzi_to_pinyin(hanzi) == expected


def test_chinese_results_show_pinyin_not_english(client):
    html = client.get("/my-name-in-chinese/find/John").get_data(as_text=True)
    assert "Yuēhàn" in html
    conn = sqlite3.connect(_WORLD_DB_PATHS["chinese"])
    assert conn.execute("SELECT name FROM names WHERE original_writing = '约翰'").fetchone()[0] == "Yuēhàn"
    assert conn.execute("SELECT COUNT(*) FROM names WHERE name = 'John'").fetchone()[0] == 0
    conn.close()


@pytest.mark.parametrize("query,hanzi", [("Yuehan", "约翰"), ("Maikeer", "迈克尔")])
def test_toneless_pinyin_finds_chinese_name_first(client, query, hanzi):
    html = client.get(f"/my-name-in-chinese/find/{query}").get_data(as_text=True)
    assert re.findall(r'original-writing[^>]*>([^<]+)<', html)[0] == hanzi


@pytest.mark.parametrize("product,query,expected", [
    ("spanish", "Michael", "Miguel"), ("spanish", "John", "Juan"), ("spanish", "Laura", "Laura"),
    ("russian", "John", "Джон"), ("chinese", "John", "约翰"),
])
def test_local_equivalent_ranks_first(product, query, expected):
    results, _ = get_similar_names(query, "auto", "sound", "", db_path=_WORLD_DB_PATHS[product], product=product)
    assert expected in (results[0][0], results[0][6])


def test_exact_spelling_match_ranks_first(client):
    html = client.get("/my-name-in-russian/find/Emma").get_data(as_text=True)
    assert html.index("Эмма") < html.index("Эме")


@pytest.mark.parametrize("product,query,expected", WORLD_EXPECTATIONS)
def test_world_finder_returns_native_names(client, product, query, expected):
    html = client.get(f"/my-name-in-{product}/find/{quote(query, safe='')}").get_data(as_text=True)
    assert expected in html
    assert '<option value="auto" selected' in html
    assert f'href="https://namefinder.dutl.uk/my-name-in-{product}/find/{quote(query, safe="")}"' in html
    assert "noindex" not in html


@pytest.mark.parametrize("product", WORLD_PRODUCTS)
@pytest.mark.parametrize("lang", list(LANGUAGES))
def test_world_finder_home_renders_in_every_language(client, product, lang):
    resp = client.get(f"/my-name-in-{product}/?lang={lang}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert get_world_page_translations(product, lang)["title"] in html
    assert "{x}" not in html


def test_world_templates_cover_every_language():
    en_keys = set(WORLD_PAGE_TEMPLATES["en"])
    assert set(WORLD_PAGE_TEMPLATES) == set(LANGUAGES) == set(WORLD_LANGUAGE_NAMES)
    for lang in LANGUAGES:
        assert set(WORLD_PAGE_TEMPLATES[lang]) == en_keys, lang
        assert set(WORLD_LANGUAGE_NAMES[lang]) == set(WORLD_PRODUCTS), lang
        for product in WORLD_PRODUCTS:
            assert TRANSLATIONS[lang][f"ad_banner_{product}_title"]


def test_world_find_redirect_uses_pretty_url(client):
    resp = client.get("/my-name-in-japanese/find?name=Yuki")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/my-name-in-japanese/find/Yuki")


def test_world_finders_linked_and_in_sitemap(client):
    home = client.get("/").get_data(as_text=True)
    for product in WORLD_PRODUCTS:
        assert f'href="/my-name-in-{product}' in home
    locs = set(re.findall(r"<loc>(.*?)</loc>", client.get("/sitemap.xml").get_data(as_text=True)))
    assert len(locs) < 50000
    for product in WORLD_PRODUCTS:
        assert f"https://namefinder.dutl.uk/my-name-in-{product}/find/John" in locs
    assert "https://namefinder.dutl.uk/my-name-in-chinese/find/Sarah" in locs
