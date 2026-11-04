"""Long-term memory of her life (user_facts): validation, dedupe, forget, consent, family view."""

import pytest
from core_api import facts
from core_api.facts import reject_reason, same_fact


def save(client, uid, fact, kind="note", **kw):
    return client.post(f"/users/{uid}/facts", json={"fact": fact, "kind": kind, **kw})


def consent(client, uid, on=True):
    client.patch(f"/users/{uid}", json={"consent_distress_alert": on})


# ---- never-store rules --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("fact", "kind", "why"),
    [
        ("तिचा फोन नंबर 9000000000", "note", "number"),
        ("नातू सात वर्षांचा आहे 7", "person", "number"),
        ("पेन्शन दर महिन्याला येते", "note", "money"),
        ("तिला पाचशे रुपये दिले", "note", "money"),
        ("पत्ता: गणेश रोड", "place", "address"),
        ("ती दररोज बीपीची गोळी घेते", "routine", "health"),
        ("तिला मधुमेह आहे", "concern", "health"),
        ("हृदयविकार आहे", "note", "health"),
        ("x", "note", "length"),
    ],
)
def test_never_stored(fact, kind, why):
    assert reject_reason(fact, kind, consent=True) == why


def test_ordinary_life_facts_pass():
    for fact, kind in [("आर्यन — नातू", "person"), ("भजन ऐकायला आवडतं", "like"), ("सकाळी तुळशीची पूजा करते", "routine"),
                       ("विमल मैत्रीण शुक्रवारी भेटायला येणार", "event"), ("बागेत फिरायला आवडतं", "place")]:
        assert reject_reason(fact, kind, consent=False) is None


def test_a_concern_needs_the_consent_flag():
    assert reject_reason("गुडघा दुखतो असं सांगितलं", "concern", consent=False) == "concern_needs_consent"
    assert reject_reason("गुडघा दुखतो असं सांगितलं", "concern", consent=True) is None


def test_the_api_refuses_with_422(client, uid):
    r = save(client, uid, "फोन 9000000000")
    assert r.status_code == 422 and "number" in r.json()["detail"]
    assert client.get(f"/users/{uid}/facts").json() == []


def test_a_concern_is_stored_only_with_consent(client, uid):
    assert save(client, uid, "गुडघा दुखतो असं सांगितलं", "concern").status_code == 422
    consent(client, uid)
    assert save(client, uid, "गुडघा दुखतो असं सांगितलं", "concern").status_code == 200


# ---- dedupe ------------------------------------------------------------------------------------------------------
def test_the_same_person_twice_is_one_row_with_the_newest_wording(client, uid):
    first = save(client, uid, "आर्यन — नातू", "person").json()
    again = save(client, uid, "आर्यन — नातू, शाळेत जातो", "person").json()
    assert first["created"] is True and again["created"] is False and again["id"] == first["id"]
    rows = client.get(f"/users/{uid}/facts").json()
    assert [r["fact"] for r in rows] == ["आर्यन — नातू, शाळेत जातो"]


def test_a_near_identical_like_updates_instead_of_duplicating(client, uid):
    save(client, uid, "भजन ऐकायला आवडतं", "like")
    r = save(client, uid, "भजन ऐकायला खूप आवडतं", "like").json()
    assert r["created"] is False
    assert len(client.get(f"/users/{uid}/facts").json()) == 1


def test_different_people_stay_separate(client, uid):
    save(client, uid, "आर्यन — नातू", "person")
    save(client, uid, "सुमन — शेजारीण", "person")
    assert len(client.get(f"/users/{uid}/facts").json()) == 2


def test_same_fact_helper():
    assert same_fact("person", "आर्यन — नातू", "person", "आर्यनला — नातवंड")
    assert not same_fact("like", "भजन आवडतं", "like", "बागकाम आवडतं")


# ---- forget and delete -----------------------------------------------------------------------------------------
def test_forget_deletes_the_best_match_only(client, uid):
    save(client, uid, "आर्यन — नातू", "person")
    save(client, uid, "भजन ऐकायला आवडतं", "like")
    gone = client.post(f"/users/{uid}/facts/forget", json={"match": "आर्यनचं नाव विसरून जा"}).json()
    assert [g["fact"] for g in gone] == ["आर्यन — नातू"]
    assert [r["fact"] for r in client.get(f"/users/{uid}/facts").json()] == ["भजन ऐकायला आवडतं"]
    assert client.post(f"/users/{uid}/facts/forget", json={"match": "काहीतरी वेगळं"}).json() == []


def test_the_family_can_delete_a_fact(client, uid):
    fid = save(client, uid, "भजन ऐकायला आवडतं", "like").json()["id"]
    assert client.delete(f"/users/{uid}/facts/{fid}").status_code == 204
    assert client.delete(f"/users/{uid}/facts/{fid}").status_code == 404


def test_a_fact_of_someone_else_cannot_be_deleted(client, uid):
    other = client.post("/users", json={"name": "Other (synthetic)"}).json()["id"]
    fid = save(client, uid, "भजन ऐकायला आवडतं", "like").json()["id"]
    assert client.delete(f"/users/{other}/facts/{fid}").status_code == 404


# ---- the family view ---------------------------------------------------------------------------------------------
def test_the_family_list_needs_the_consent_flag_but_arjun_always_sees_them(client, uid):
    save(client, uid, "भजन ऐकायला आवडतं", "like")
    assert client.get(f"/users/{uid}/facts", params={"audience": "family"}).json() == []
    assert len(client.get(f"/users/{uid}/facts").json()) == 1
    consent(client, uid)
    rows = client.get(f"/users/{uid}/facts", params={"audience": "family"}).json()
    assert [r["fact"] for r in rows] == ["भजन ऐकायला आवडतं"]
    assert set(rows[0]) == {"id", "fact", "kind", "source_date", "last_used", "confidence", "source"}  # no transcript


def test_used_marks_the_time(client, uid):
    fid = save(client, uid, "भजन ऐकायला आवडतं", "like").json()["id"]
    assert client.post(f"/users/{uid}/facts/{fid}/used").status_code == 204
    assert client.get(f"/users/{uid}/facts").json()[0]["last_used"] is not None


def test_the_cap_removes_the_least_used_automatic_fact(client, uid, monkeypatch):
    monkeypatch.setattr(facts, "MAX_FACTS", 3)
    for n, word in enumerate(["अ", "ब", "क", "ड"]):
        assert save(client, uid, f"तुळस{word}फूल बाग{word}{word}", "like").status_code == 200, n
    assert len(client.get(f"/users/{uid}/facts").json()) == 3
