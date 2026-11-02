"""Apps and links (voice-controlled apps, task 1): family CRUD with validated values. No network."""

import pytest

VIDEO = "dQw4w9WgXcQ"
PLAYLIST = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
CHANNEL = "UCZFMm1mMw0F81Z37aaEzTUA"


def add(client, uid, **body):
    return client.post(f"/users/{uid}/app-links", json=body)


def test_family_can_add_list_edit_and_delete(client, uid):
    r = add(client, uid, kind="youtube_playlist", label="भक्तिगीते", value=PLAYLIST,
            spoken_names=["भक्तिगीते", "bhajan", "भजन", "भजन"])
    assert r.status_code == 201
    row = r.json()
    assert row["spoken_names"] == ["भक्तिगीते", "bhajan", "भजन"] and row["other_host"] is False
    assert client.get(f"/users/{uid}/app-links").json()[0]["id"] == row["id"]
    r = client.patch(f"/users/{uid}/app-links/{row['id']}", json={"label": "देवाची गाणी", "sort": 3})
    assert r.json()["label"] == "देवाची गाणी" and r.json()["sort"] == 3
    assert client.delete(f"/users/{uid}/app-links/{row['id']}").status_code == 204
    assert client.get(f"/users/{uid}/app-links").json() == []


@pytest.mark.parametrize(
    "value",
    [
        "http://www.loksatta.com/rss",  # http is never allowed
        "ftp://www.loksatta.com/rss",
        "javascript:alert(1)",
        "https://127.0.0.1/rss",
        "https://localhost/rss",
        "https://user:pw@www.loksatta.com/rss",
        "https://192.168.0.5/feed",
    ],
)
def test_unsafe_urls_are_rejected_even_with_approval(client, uid, value):
    r = add(client, uid, kind="rss", label="x", value=value, allow_other_host=True)
    assert r.status_code == 422


def test_unknown_host_needs_explicit_family_approval_and_is_flagged(client, uid):
    url = "https://news.example.org/feed.xml"
    assert add(client, uid, kind="rss", label="Example", value=url).status_code == 422
    ok = add(client, uid, kind="rss", label="Example", value=url, allow_other_host=True)
    assert ok.status_code == 201 and ok.json()["other_host"] is True  # the dashboard shows a warning for it


def test_known_hosts_need_no_approval_and_subdomains_match(client, uid):
    r = add(client, uid, kind="rss", label="ABP", value="https://marathi.abplive.com/feed")
    assert r.status_code == 201 and r.json()["other_host"] is False
    r = add(client, uid, kind="link", label="नातवाचे फोटो", value="https://photos.google.com/share/abc")
    assert r.status_code == 201
    # a look-alike host is NOT a subdomain match
    assert add(client, uid, kind="rss", label="x", value="https://loksatta.com.evil.io/rss").status_code == 422


def test_youtube_values_are_checked_and_urls_are_reduced_to_ids(client, uid):
    r = add(client, uid, kind="youtube_video", label="v", value=f"https://www.youtube.com/watch?v={VIDEO}&t=3")
    assert r.json()["value"] == VIDEO
    r = add(client, uid, kind="youtube_video", label="v2", value=f"https://youtu.be/{VIDEO}")
    assert r.json()["value"] == VIDEO
    r = add(client, uid, kind="youtube_playlist", label="p", value=f"https://www.youtube.com/playlist?list={PLAYLIST}")
    assert r.json()["value"] == PLAYLIST
    r = add(client, uid, kind="youtube_channel_live", label="n", value=f"https://www.youtube.com/channel/{CHANNEL}")
    assert r.json()["value"] == CHANNEL
    assert add(client, uid, kind="youtube_video", label="bad", value="not an id").status_code == 422
    assert add(client, uid, kind="youtube_video", label="bad", value="https://evil.io/watch?v=" + VIDEO).status_code == 422
    assert add(client, uid, kind="youtube_channel_live", label="bad", value="@somehandle").status_code == 422
    assert add(client, uid, kind="youtube_query", label="q", value="https://x.io").status_code == 422
    assert add(client, uid, kind="youtube_query", label="भजन", value="भीमसेन जोशी भजन").status_code == 201


def test_whatsapp_points_at_an_existing_contact_and_never_stores_a_number(client, uid):
    c = client.post(f"/users/{uid}/contacts", json={"name": "चंद्रकांत", "phone": "9000000001"}).json()
    r = add(client, uid, kind="whatsapp", label="चंद्रकांत", value=str(c["id"]), spoken_names=["चंद्रकांत"])
    assert r.status_code == 201 and r.json()["value"] == str(c["id"])
    assert "9000000001" not in r.text
    assert add(client, uid, kind="whatsapp", label="x", value="9000000001").status_code == 422  # a number, not a contact
    assert add(client, uid, kind="whatsapp", label="x", value="999").status_code == 422  # no such contact


def test_a_contact_of_another_user_cannot_be_used(client, uid):
    other = client.post("/users", json={"name": "Other (synthetic)"}).json()["id"]
    c = client.post(f"/users/{other}/contacts", json={"name": "Z", "phone": "1"}).json()
    assert add(client, uid, kind="whatsapp", label="Z", value=str(c["id"])).status_code == 422


def test_another_users_link_is_not_reachable(client, uid):
    other = client.post("/users", json={"name": "Other (synthetic)"}).json()["id"]
    row = add(client, uid, kind="youtube_query", label="गाणी", value="जुनी मराठी गाणी").json()
    assert client.delete(f"/users/{other}/app-links/{row['id']}").status_code == 404
    assert client.patch(f"/users/{other}/app-links/{row['id']}", json={"label": "x"}).status_code == 404
    assert client.get("/users/999/app-links").status_code == 404
