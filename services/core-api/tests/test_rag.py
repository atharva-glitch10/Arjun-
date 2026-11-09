"""Light RAG over stories: stored locally, searched by similarity, private to the elder, forgotten on delete."""


def _user(client):
    return client.post("/users", json={"name": "Test Aaji"}).json()["id"]


def _story(client, uid, text):
    r = client.post(f"/users/{uid}/stories", json={"summary": text})
    assert r.status_code == 201
    return r.json()["id"]


def test_search_returns_the_related_story_first(client):
    uid = _user(client)
    a = _story(client, uid, "Aaji grew tomatoes on the balcony in Pune and shared them with neighbours")
    _story(client, uid, "Her wedding day was in May with a long train journey to Nashik")
    hits = client.get(f"/users/{uid}/stories/search", params={"q": "tell me about the tomatoes"}).json()
    assert hits and hits[0]["id"] == a
    assert hits[0]["summary"].startswith("Aaji grew tomatoes")


def test_devanagari_story_is_found(client):
    uid = _user(client)
    a = _story(client, uid, "लहानपणी आम्ही गावातल्या नदीवर पोहायला जायचो")
    _story(client, uid, "बाजारातून भाजी आणली आणि जेवण केलं")
    hits = client.get(f"/users/{uid}/stories/search", params={"q": "नदीवर पोहायला"}).json()
    assert hits and hits[0]["id"] == a


def test_unrelated_query_returns_nothing(client):
    uid = _user(client)
    _story(client, uid, "Her wedding day was in May")
    assert client.get(f"/users/{uid}/stories/search", params={"q": "zzzqqq xyzxyz"}).json() == []


def test_search_is_per_user(client):
    u1, u2 = _user(client), _user(client)
    _story(client, u1, "tomatoes on the balcony")
    assert client.get(f"/users/{u2}/stories/search", params={"q": "tomatoes"}).json() == []


def test_forgotten_story_is_gone_from_search_and_index(client):
    uid = _user(client)
    sid = _story(client, uid, "tomatoes on the balcony")
    assert client.delete(f"/users/{uid}/stories/{sid}").status_code == 204
    assert client.get(f"/users/{uid}/stories/search", params={"q": "tomatoes"}).json() == []


def test_story_saved_by_confirmed_action_is_indexed(client):
    uid = _user(client)
    r = client.post(f"/users/{uid}/actions/propose", json={"action_type": "SAVE_STORY", "payload": {"summary": "tomatoes on the balcony"}})
    assert client.post(f"/users/{uid}/actions/{r.json()['id']}/confirm").status_code == 200
    hits = client.get(f"/users/{uid}/stories/search", params={"q": "tomatoes"}).json()
    assert len(hits) == 1


def test_old_stories_are_backfilled(client):
    from core_api import models as m
    from core_api.main import app, get_db

    uid = _user(client)
    db = next(app.dependency_overrides[get_db]())
    db.add(m.StoryMemory(user_id=uid, summary="tomatoes on the balcony", share_status="private"))
    db.commit()
    assert len(client.get(f"/users/{uid}/stories/search", params={"q": "tomatoes"}).json()) == 1
