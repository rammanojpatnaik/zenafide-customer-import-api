from app.models import ImportJob
from app.services.security import create_access_token


def test_login_returns_bearer_token_and_me_returns_user(client):
    login_response = client.post(
        "/auth/login",
        data={"username": "operator@example.com", "password": "test-password"},
    )

    assert login_response.status_code == 200
    token = login_response.json()
    assert token["token_type"] == "bearer"
    assert token["access_token"]

    me_response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "operator@example.com"
    assert me_response.json()["role"] == "operator"


def test_login_rejects_invalid_password(client):
    response = client.post(
        "/auth/login",
        data={"username": "operator@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_customer_routes_require_authentication(client):
    response = client.get("/customers", headers={"Authorization": ""})

    assert response.status_code == 401


def test_operator_cannot_delete_customer(client):
    create_response = client.post(
        "/customers",
        json={
            "partner_id": "p1",
            "partner_customer_id": "C1001",
            "email": "ada@example.com",
            "name": "Ada Lovelace",
        },
    )
    customer_id = create_response.json()["id"]

    response = client.delete(
        f"/customers/{customer_id}",
        headers={
            "Authorization": f"Bearer {create_access_token('operator@example.com')}"
        },
    )

    assert response.status_code == 403


def test_import_tracks_authenticated_uploader(client, db_session):
    response = client.post(
        "/imports/customers",
        files={
            "file": (
                "customers.csv",
                "p,row,cid,email,name,status,tier,upd,tags,note\n"
                "p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 202
    import_job = db_session.get(ImportJob, response.json()["id"])
    assert import_job.uploaded_by is not None
    assert import_job.uploaded_by_user.email == "admin@example.com"
