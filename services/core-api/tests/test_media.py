"""YouTube search (cache, quota) and news headlines (fixture RSS, Devanagari). The Google API and the feeds are
mocked: no real network in tests."""

import httpx
import pytest
from core_api import media

FEED_A = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>लोकसत्ता</title>
<item><title>मुंबईत आज जोरदार पाऊस</title></item>
<item><title><![CDATA[<b>पुणे</b> मेट्रोचा नवा मार्ग &amp; वेळापत्रक]]></title></item>
<item><title>तिसरी बातमी</title></item>
<item><title>चौथी बातमी</title></item>
</channel></rss>""".encode()
FEED_B = """<?xml version="1.0" encoding="UTF-8"?>
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


def google_ok(videos):
    return {"items": [{"id": {"videoId": v}, "snippet": {"title": f"{t} &amp; more", "channelTitle": "Ch &#39;1&#39;"}}
                      for v, t in videos]}


class FakeGoogle:
    def __init__(self, status=200, body=None, text=None):
        self.calls = []
        self.status, self.body, self.text = status, body, text

    def __call__(self, url, params=None, timeout=5.0):
        self.calls.append((url, params))
        if self.text is not None:
            return httpx.Response(self.status, text=self.text)
        return httpx.Response(self.status, json=self.body)


# ---- YouTube ------------------------------------------------------------------------------------------------
def test_no_key_means_503_so_reasoning_can_open_the_results_page(client, uid):
    r = client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})
    assert r.status_code == 503 and r.json()["detail"] == "youtube_not_configured"


def test_search_sends_the_safe_parameters_and_returns_clean_rows(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    g = FakeGoogle(body=google_ok([("AAAAAAAAAAA", "भीमसेन जोशी भजन"), ("BBBBBBBBBBB", "दुसरं")]))
    monkeypatch.setattr(media, "http_get", g)
    r = client.get("/media/youtube/search", params={"q": "भीमसेन जोशी भजन", "user_id": uid})
    assert r.status_code == 200
    assert r.json()[0] == {"video_id": "AAAAAAAAAAA", "title": "भीमसेन जोशी भजन & more", "channel": "Ch '1'"}
    _, p = g.calls[0]
    assert p["type"] == "video" and p["videoEmbeddable"] == "true" and p["safeSearch"] == "strict"
    assert p["relevanceLanguage"] == "mr" and p["regionCode"] == "IN" and p["maxResults"] == 8


def test_ranking_prefers_the_title_with_most_query_words(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    body = {"items": [
        {"id": {"videoId": "AAAAAAAAAAA"}, "snippet": {"title": "भजन", "channelTitle": "Ch"}},
        {"id": {"videoId": "BBBBBBBBBBB"}, "snippet": {"title": "भीमसेन जोशी भजन", "channelTitle": "Ch"}},
    ]}
    monkeypatch.setattr(media, "http_get", FakeGoogle(body=body))
    r = client.get("/media/youtube/search", params={"q": "भीमसेन जोशी भजन", "user_id": uid})
    assert [x["video_id"] for x in r.json()] == ["BBBBBBBBBBB", "AAAAAAAAAAA"]


def test_shorts_and_titles_with_none_of_the_words_are_skipped(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    body = {"items": [
        {"id": {"videoId": "AAAAAAAAAAA"}, "snippet": {"title": "भजन #shorts", "channelTitle": "Ch"}},
        {"id": {"videoId": "BBBBBBBBBBB"}, "snippet": {"title": "क्रिकेट सामना", "channelTitle": "Ch"}},
        {"id": {"videoId": "CCCCCCCCCCC"}, "snippet": {"title": "भीमसेन जोशी भजन", "channelTitle": "Ch"}},
    ]}
    g = FakeGoogle(body=body)
    monkeypatch.setattr(media, "http_get", g)
    r = client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})
    assert [x["video_id"] for x in r.json()] == ["CCCCCCCCCCC"]
    # a non-empty answer is cached
    assert client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid}).json() == r.json()
    assert len(g.calls) == 1


def test_an_empty_answer_is_not_cached(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    body = {"items": [
        {"id": {"videoId": "AAAAAAAAAAA"}, "snippet": {"title": "भजन #shorts", "channelTitle": "Ch"}},
        {"id": {"videoId": "BBBBBBBBBBB"}, "snippet": {"title": "क्रिकेट सामना", "channelTitle": "Ch"}},
    ]}
    g = FakeGoogle(body=body)
    monkeypatch.setattr(media, "http_get", g)
    assert client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid}).json() == []
    assert client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid}).json() == []
    assert len(g.calls) == 2


def test_news_search_is_the_newest_uploads_not_live_streams_and_keeps_a_live_title_with_no_query_match(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    body = {"items": [
        {"id": {"videoId": "AAAAAAAAAAA"}, "snippet": {"title": "मुंबईत पाऊस", "channelTitle": "Ch"}},
        {"id": {"videoId": "BBBBBBBBBBB"}, "snippet": {"title": "मराठी बातम्या LIVE", "channelTitle": "Ch"}},
        {"id": {"videoId": "CCCCCCCCCCC"}, "snippet": {"title": "मराठी बातम्या #shorts", "channelTitle": "Ch"}},
    ]}
    g = FakeGoogle(body=body)
    monkeypatch.setattr(media, "http_get", g)
    r = client.get("/media/youtube/search", params={"q": "", "kind": "news_video", "user_id": uid})
    assert [x["video_id"] for x in r.json()] == ["BBBBBBBBBBB", "AAAAAAAAAAA"]
    _, p = g.calls[0]
    assert "eventType" not in p and p["order"] == "date" and p["publishedAfter"].endswith("Z")
    assert p["q"] == "मराठी बातम्या" and p["maxResults"] == 8


def test_media_status_reports_the_key_and_the_last_error(client, uid, monkeypatch):
    assert client.get("/media/status").json() == {"youtube_key": False, "last_error": None}
    client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})  # no key
    assert client.get("/media/status").json()["last_error"] == "503 youtube_not_configured"
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    assert client.get("/media/status").json()["youtube_key"] is True


def test_a_repeated_query_is_served_from_the_cache(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    g = FakeGoogle(body=google_ok([("AAAAAAAAAAA", "Lata Mangeshkar song")]))
    monkeypatch.setattr(media, "http_get", g)
    for q in ("Lata  Mangeshkar", "lata mangeshkar", " LATA mangeshkar "):  # normalised: one key
        assert client.get("/media/youtube/search", params={"q": q, "user_id": uid}).status_code == 200
    assert len(g.calls) == 1


def test_the_cache_expires_after_24_hours(client, uid, monkeypatch):
    from datetime import datetime, timedelta

    from core_api.main import app, get_now

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    g = FakeGoogle(body=google_ok([("AAAAAAAAAAA", "भजन")]))
    monkeypatch.setattr(media, "http_get", g)
    base = app.dependency_overrides[get_now]()
    client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})
    app.dependency_overrides[get_now] = lambda: base + timedelta(hours=23)
    client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})
    assert len(g.calls) == 1
    app.dependency_overrides[get_now] = lambda: base + timedelta(hours=25)
    client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid})
    assert len(g.calls) == 2
    app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 6, 9, 0)


def test_google_quota_error_stops_further_calls_for_the_day(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    g = FakeGoogle(status=403, text='{"error": {"errors": [{"reason": "quotaExceeded"}]}}')
    monkeypatch.setattr(media, "http_get", g)
    r = client.get("/media/youtube/search", params={"q": "एक", "user_id": uid})
    assert r.status_code == 429 and r.json()["detail"] == "youtube_quota"
    r = client.get("/media/youtube/search", params={"q": "दोन", "user_id": uid})
    assert r.status_code == 429 and len(g.calls) == 1  # the second one never reached Google


def test_our_own_daily_cap_is_enforced(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("YOUTUBE_MAX_SEARCHES_PER_DAY", "2")
    g = FakeGoogle(body=google_ok([("AAAAAAAAAAA", "गाणं")]))
    monkeypatch.setattr(media, "http_get", g)
    codes = [client.get("/media/youtube/search", params={"q": f"गाणं {i}", "user_id": uid}).status_code
             for i in range(4)]
    assert codes == [200, 200, 429, 429] and len(g.calls) == 2
    # a cached query still works when the cap is reached
    assert client.get("/media/youtube/search", params={"q": "गाणं 0", "user_id": uid}).status_code == 200


def test_network_failure_is_a_502_and_is_not_cached(client, uid, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

    def boom(url, params=None, timeout=5.0):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(media, "http_get", boom)
    assert client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid}).status_code == 502
    monkeypatch.setattr(media, "http_get", FakeGoogle(body=google_ok([("AAAAAAAAAAA", "x")])))
    assert client.get("/media/youtube/search", params={"q": "भजन", "user_id": uid}).status_code == 200


# ---- news ---------------------------------------------------------------------------------------------------
def add_feed(client, uid, label, url):
    r = client.post(f"/users/{uid}/app-links", json={"kind": "rss", "label": label, "value": url})
    assert r.status_code == 201, r.text


def feeds(mapping):
    calls = []

    def get(url, params=None, timeout=5.0):
        calls.append(url)
        body = mapping[url]
        if isinstance(body, Exception):
            raise body
        return httpx.Response(200, content=body)

    get.calls = calls
    return get


def test_parse_rss_and_atom_with_devanagari_cdata_and_html():
    assert media.parse_feed_titles(FEED_A)[:2] == ["मुंबईत आज जोरदार पाऊस", "पुणे मेट्रोचा नवा मार्ग & वेळापत्रक"]
    assert media.parse_feed_titles(FEED_B) == ["शेतकऱ्यांसाठी नवी योजना", "क्रिकेट: भारताचा विजय"]
    assert media.parse_feed_titles(b"<html>not a feed") == []


def test_titles_are_cut_at_120_characters_and_never_rewritten():
    long = "बातमी " * 40
    cleaned = media.clean_title(f"<p>{long}</p>")
    assert len(cleaned) <= 120 and cleaned.startswith("बातमी बातमी")


def test_top_five_interleave_the_feeds_and_name_the_source(client, uid, monkeypatch):
    add_feed(client, uid, "लोकसत्ता", "https://www.loksatta.com/feed")
    add_feed(client, uid, "सकाळ", "https://www.esakal.com/feed")
    monkeypatch.setattr(media, "http_get", feeds({
        "https://www.loksatta.com/feed": FEED_A, "https://www.esakal.com/feed": FEED_B}))
    items = client.get("/media/news", params={"user_id": uid}).json()
    assert len(items) == 5
    assert [i["source_label"] for i in items] == ["लोकसत्ता", "सकाळ", "लोकसत्ता", "सकाळ", "लोकसत्ता"]
    assert items[1]["title"] == "शेतकऱ्यांसाठी नवी योजना"


def test_news_is_cached_for_15_minutes(client, uid, monkeypatch):
    add_feed(client, uid, "लोकसत्ता", "https://www.loksatta.com/feed")
    f = feeds({"https://www.loksatta.com/feed": FEED_A})
    monkeypatch.setattr(media, "http_get", f)
    t = [1000.0]
    monkeypatch.setattr(media, "_clock", lambda: t[0])
    client.get("/media/news", params={"user_id": uid})
    t[0] += 14 * 60
    client.get("/media/news", params={"user_id": uid})
    assert len(f.calls) == 1
    t[0] += 2 * 60
    client.get("/media/news", params={"user_id": uid})
    assert len(f.calls) == 2


def test_one_broken_feed_does_not_stop_the_other(client, uid, monkeypatch):
    add_feed(client, uid, "लोकसत्ता", "https://www.loksatta.com/feed")
    add_feed(client, uid, "सकाळ", "https://www.esakal.com/feed")
    monkeypatch.setattr(media, "http_get", feeds({
        "https://www.loksatta.com/feed": httpx.ConnectTimeout("slow"), "https://www.esakal.com/feed": FEED_B}))
    items = client.get("/media/news", params={"user_id": uid}).json()
    assert [i["source_label"] for i in items] == ["सकाळ", "सकाळ"]


def test_no_feeds_or_all_failing_gives_an_empty_list_and_is_not_cached(client, uid, monkeypatch):
    assert client.get("/media/news", params={"user_id": uid}).json() == []
    add_feed(client, uid, "लोकसत्ता", "https://www.loksatta.com/feed")
    f = feeds({"https://www.loksatta.com/feed": httpx.ConnectError("down")})
    monkeypatch.setattr(media, "http_get", f)
    assert client.get("/media/news", params={"user_id": uid}).json() == []
    monkeypatch.setattr(media, "http_get", feeds({"https://www.loksatta.com/feed": FEED_A}))
    assert len(client.get("/media/news", params={"user_id": uid}).json()) == 4


def test_a_long_title_ends_at_a_whole_word():
    words = ["शेतकऱ्यांसाठी", "नवी", "योजना", "जाहीर"] * 12
    cleaned = media.clean_title(" ".join(words))
    assert len(cleaned) <= 120 and cleaned.endswith("…")
    assert cleaned[:-1].split(" ")[-1] in words  # the last word is complete, not half of one
