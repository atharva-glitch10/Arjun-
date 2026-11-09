def test_contact_can_be_fixed_and_removed(client, uid):
    c = client.post(f"/users/{uid}/contacts", json={"name": "चंद्रकांत", "relation": "मुलगा", "phone": "00000 00003"}).json()
    r = client.patch(f"/users/{uid}/contacts/{c['id']}", json={"name": "चंद्रकांत", "relation": "मुलगा", "phone": "9356308607"})
    assert r.status_code == 200 and r.json()["phone"] == "9356308607"
    assert client.delete(f"/users/{uid}/contacts/{c['id']}").status_code == 204
    assert client.get(f"/users/{uid}/contacts").json() == []
    assert client.patch(f"/users/{uid}/contacts/999999", json={"name": "x"}).status_code == 404
