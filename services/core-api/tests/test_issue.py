""" "I am facing an issue": a family alert of kind `issue`, urgent on the feed, and the alarm rings.

This is not an emergency (no 112) and not medical advice. It is a help signal that always reaches the family
dashboard, like a help request.
"""


def test_an_issue_creates_an_urgent_family_alert(client, uid):
    r = client.post(f"/users/{uid}/issue")
    assert r.status_code == 201, r.text
    assert r.json()["family_told"] is True

    notes = client.get(f"/users/{uid}/notifications").json()
    assert [n["kind"] for n in notes] == ["issue"]
    assert "issue" in notes[0]["body"].lower()
    feed = client.get(f"/users/{uid}/feed").json()
    assert feed[-1]["kind"] == "issue" and feed[-1]["severity"] == "urgent"


def test_the_alert_is_honest_that_no_call_or_message_was_sent(client, uid):
    client.post(f"/users/{uid}/issue")
    body = client.get(f"/users/{uid}/notifications").json()[0]["body"]
    assert "no call or message was sent" in body.lower()
    assert "112" not in body


def test_an_issue_for_a_missing_user_is_404(client):
    assert client.post("/users/999/issue").status_code == 404
