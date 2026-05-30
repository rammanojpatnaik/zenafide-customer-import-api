def customer_payload(**overrides):
    payload = {
        "partner_id": "p1",
        "partner_customer_id": "C1001",
        "email": "ada@example.com",
        "name": "Ada Lovelace",
        "status": "active",
        "tier": "ent",
        "tags": "vip",
        "note": "manual create",
    }
    payload.update(overrides)
    return payload


def test_customer_crud_flow(client):
    create_response = client.post("/customers", json=customer_payload())

    assert create_response.status_code == 201
    customer = create_response.json()
    assert customer["id"]
    assert customer["email"] == "ada@example.com"
    assert customer["tier"] == "ent"

    list_response = client.get("/customers", params={"partner_id": "p1"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    get_response = client.get(f"/customers/{customer['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Ada Lovelace"

    update_response = client.patch(
        f"/customers/{customer['id']}",
        json={"tier": "pro", "internal_note": "updated by operator"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["tier"] == "pro"
    assert update_response.json()["internal_note"] == "updated by operator"

    delete_response = client.delete(f"/customers/{customer['id']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/customers/{customer['id']}")
    assert missing_response.status_code == 404


def test_customer_create_rejects_duplicate_partner_identity(client):
    first_response = client.post("/customers", json=customer_payload())
    duplicate_response = client.post("/customers", json=customer_payload())

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_customer_validation_rejects_invalid_email_status_and_tier(client):
    invalid_email_response = client.post(
        "/customers",
        json=customer_payload(email="not-an-email"),
    )
    invalid_status_response = client.post(
        "/customers",
        json=customer_payload(status="paused"),
    )
    invalid_tier_response = client.post(
        "/customers",
        json=customer_payload(tier="starter"),
    )

    assert invalid_email_response.status_code == 422
    assert invalid_status_response.status_code == 422
    assert invalid_tier_response.status_code == 422


def test_customer_update_rejects_conflicting_identity(client):
    first = client.post("/customers", json=customer_payload()).json()
    second = client.post(
        "/customers",
        json=customer_payload(
            partner_customer_id="C1002",
            email="grace@example.com",
            name="Grace Hopper",
        ),
    ).json()

    conflict_response = client.patch(
        f"/customers/{second['id']}",
        json={"partner_customer_id": first["partner_customer_id"]},
    )

    assert conflict_response.status_code == 409
