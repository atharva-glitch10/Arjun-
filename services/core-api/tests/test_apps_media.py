"""The `/apps` face of family links, spoken-name match, YouTube fallback and `/users/{id}/news`.

The Google API and every feed are mocked: no real network in tests.
"""

from urllib.parse import quote

import httpx
import pytest
from core_api import media

PLAYLIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
PLAYLIST_2 = "PLsecond00000000000000000000000000000000"
CHANNEL = "UCZFMm1mMw0F81Z37aaEzTUA"

FEED_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>लोकसत्ता</title>
<item><title>मुंबईत आज जोरदार पाऊस</title></item>
<item><title><![CDATA[<b>पुणे</b> मेट्रोचा नवा मार्ग &amp; वेळापत्रक]]></title></item>
<item><title>तिसरी बातमी</title></item>
<item><title>चौथी बातमी</title></item>
</channel></rss>""".encode()
FEED_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>सकाळ</title>
<entry><title>शेतकऱ्यांसाठी नवी योजना</title></entry>
<entry><title>क्रिकेट: भारताचा विजय</title></entry>
</feed>""".encode()


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    media.reset_quota_for_tests()
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_MAX_SEARCHES_PER_DAY", raising=False)
    yield
    media.reset_quota_for_tests()


def add(client, uid, **body):
    return client.post(f"/users/{uid}/apps", json=body)


# ---- /apps CRUD and validation ------------------------------------------------------------------------------
def test_apps_alias_crud_and_youtube_live_short_name(client, uid):
    r = add(client, uid, kind="youtube_live", label="बातम्या", value=CHANNEL,
            spoken_names=["बातम्या", "न्यूज", "बातम्या"])
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["kind"] == "youtube_channel_live"  # stored under the kind the elder screen knows
    assert row["spoken_names"] == ["बातम्या", "न्यूज"]  # lower-cased, de-duplicated
    assert row["approved_by_family"] is False and row["other_host"] is False
    assert client.get(f"/users/{uid}/apps").json()[0]["id"] == row["id"]
    patched = client.patch(f"/users/{uid}/apps/{row['id']}", json={"label": "टीव्ही बातम्या", "sort": 2})
    assert patched.json()["label"] == "टीव्ही बातम्या" and patched.json()["sort"] == 2
    assert client.delete(f"/users/{uid}/apps/{row['id']}").status_code == 204
    assert client.get(f"/users/{uid}/apps").json() == []


def test_apps_reject_http_and_foreign_youtube_hosts(client, uid):
    assert add(client, uid, kind="link", label="x", value="http://www.loksatta.com").status_code == 422
    assert add(client, uid, kind="youtube_video", label="x",
               value="https://vimeo.com/12345678901").status_code == 422
    assert add(client, uid, kind="youtube_playlist", label="x",
               value="https://evil.io/playlist?list=" + PLAYLIST).status_code == 422


def test_apps_whatsapp_value_must_be_her_own_contact(client, uid):
    assert add(client, uid, kind="whatsapp", label="x", value="9000000001").status_code == 422
    c = client.post(f"/users/{uid}/contacts", json={"name": "चंद्रकांत", "phone": "9000000001"}).json()
    ok = add(client, uid, kind="whatsapp", label="चंद्रकांत", value=str(c["id"]))
    assert ok.status_code == 201 and "9000000001" not in ok.text
    other = client.post("/users", json={"name": "Other (synthetic)"}).json()["id"]
    foreign = client.post(f"/users/{other}/contacts", json={"name": "Z", "phone": "1"}).json()
    assert add(client, uid, kind="whatsapp", label="Z", value=str(foreign["id"])).status_code == 422


def test_an_unlisted_rss_host_needs_approval_and_is_flagged_for_the_dashboard(client, uid):
    url = "https://news.example.org/feed.xml"
    assert add(client, uid, kind="rss", label="Example", value=url).status_code == 422
    ok = add(client, uid, kind="rss", label="Example", value=url, allow_other_host=True)
    assert ok.status_code == 201
    assert ok.json()["approved_by_family"] is True and ok.json()["other_host"] is True


# ---- spoken-name match --------------------------------------------------------------------------------------
def test_match_finds_by_spoken_name_or_label_using_whole_words(client, uid):
    bhajan = add(client, uid, kind="youtube_playlist", label="भक्तिगीते", value=PLAYLIST,
                 spoken_names=["भक्तिगीते", "भजन", "Bhajan"]).json()
    special = add(client, uid, kind="youtube_playlist", label="भजन स्पेशल", value=PLAYLIST_2,
                  sort=1).json()
    hit = client.get(f"/users/{uid}/apps/match", params={"q": "आज भक्तिगीते लाव"}).json()
    assert hit["id"] == bhajan["id"]
    assert client.get(f"/users/{uid}/apps/match", params={"q": "BHAJAN लाव"}).json()["id"] == bhajan["id"]
    # the longest matching name wins: "भजन स्पेशल" covers more of what she said than "भजन"
    assert client.get(f"/users/{uid}/apps/match", params={"q": "भजन स्पेशल लाव"}).json()["id"] == special["id"]
    # never a substring: "भक्तिगीतेचं" is a different word
    assert client.get(f"/users/{uid}/apps/match", params={"q": "भक्तिगीतेचं लाव"}).json() is None
    assert client.get(f"/users/{uid}/apps/match", params={"q": "बातम्या लाव"}).json() is None


# ---- YouTube search: cache, no key, network error -----------------------------------------------------------
class FakeGoogle:
    def __init__(self, body=None, status=200, text=None, exc=None):
        self.calls = []
        self.body, self.status, self.text, self.exc = body, status, text, exc

    def __call__(self, url, params=None, timeout=5.0):
        self.calls.append((url, params))
        if self.exc is not None:
            raise self.exc
        if self.text is not None:
            return httpx.Response(self.status, text=self.text)
        return httpx.Response(self.status, json=self.body)


def google_body(video="AAAAAAAAAAA", title="भीमसेन जोशी भजन"):
    return {"items": [{"id": {"videoId": video},
                       "snippet": {"title": title, "channelTitle": "चॅनेल"}}]}


def test_search_results_are_cached_and_the_key_never_leaks(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret-key")
    g = FakeGoogle(body=google_body())
    monkeypatch.setattr(media, "http_get", g)
    first = client.get("/media/youtube/search", params={"q": "भीमसेन जोशी", "user_id": uid})
    assert first.status_code == 200
    assert first.json() == [{"video_id": "AAAAAAAAAAA", "title": "भीमसेन जोशी भजन", "channel": "चॅनेल"}]
    second = client.get("/media/youtube/search", params={"q": "  भीमसेन   जोशी ", "user_id": uid})
    assert second.json() == first.json() and len(g.calls) == 1  # served from the 24 h cache
    assert "secret-key" not in first.text and "secret-key" not in second.text
    assert g.calls[0][1]["key"] == "secret-key"  # only core-api sends it, to Google


def test_no_key_returns_the_results_page_to_open(client, uid):
    r = client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})
    assert r.status_code == 503 and r.json()["detail"] == "youtube_not_configured"
    assert r.json()["fallback_url"] == "https://www.youtube.com/results?search_query=" + quote("भजन")


def test_network_error_returns_the_results_page_to_open(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setattr(media, "http_get", FakeGoogle(exc=httpx.ConnectError("down")))
    r = client.get("/media/youtube/search", params={"q": "जुनी गाणी", "user_id": uid})
    assert r.status_code == 502 and r.json()["detail"] == "youtube_unreachable"
    assert r.json()["fallback_url"] == "https://www.youtube.com/results?search_query=" + quote("जुनी गाणी")


# ---- /users/{id}/news ----------------------------------------------------------------------------------------
def add_feed(client, uid, label, url):
    r = client.post(f"/users/{uid}/apps", json={"kind": "rss", "label": label, "value": url})
    assert r.status_code == 201, r.text


def feeds(mapping):
    def get(url, params=None, timeout=5.0):
        body = mapping[url]
        if isinstance(body, Exception):
            raise body
        return httpx.Response(200, content=body)

    return get


def test_user_news_returns_five_newest_with_verbatim_sources(client, uid, monkeypatch):
    add_feed(client, uid, "लोकसत्ता", "https://www.loksatta.com/feed")
    add_feed(client, uid, "सकाळ", "https://www.esakal.com/feed")
    add_feed(client, uid, "तुटलेला", "https://marathi.abplive.com/feed")
    monkeypatch.setattr(media, "http_get", feeds({
        "https://www.loksatta.com/feed": FEED_RSS,
        "https://www.esakal.com/feed": FEED_ATOM,
        "https://marathi.abplive.com/feed": b"<html>not a feed",
    }))
    items = client.get(f"/users/{uid}/news").json()
    assert [i["source"] for i in items] == ["लोकसत्ता", "सकाळ", "लोकसत्ता", "सकाळ", "लोकसत्ता"]
    assert items[0] == {"source": "लोकसत्ता", "title": "मुंबईत आज जोरदार पाऊस"}
    assert items[2]["title"] == "पुणे मेट्रोचा नवा मार्ग & वेळापत्रक"  # HTML tags stripped, entity decoded


def test_user_news_is_empty_when_every_feed_fails(client, uid, monkeypatch):
    add_feed(client, uid, "लोकसत्ता", "https://www.loksatta.com/feed")
    monkeypatch.setattr(media, "http_get", feeds({"https://www.loksatta.com/feed": httpx.ConnectError("down")}))
    assert client.get(f"/users/{uid}/news").json() == []
