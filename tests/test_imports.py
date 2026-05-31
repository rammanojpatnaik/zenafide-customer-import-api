from pathlib import Path


def upload_csv(client, csv_text, filename="customers.csv"):
    return client.post(
        "/imports/customers",
        files={"file": (filename, csv_text, "text/csv")},
    )


def test_import_records_row_errors_and_continues(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email
p1,002,C1002,grace@x.io,Grace Hopper,active,pro,20260420,compiler,billing
p1,003,C1003,bad-email,Hedy Lamarr,active,pro,20260420,wireless,bad-email
p1,004,C1004,annie@x.io,Annie Easley,active,start,20260420,math,bad-tier
"""

    response = upload_csv(client, csv_text)

    assert response.status_code == 201
    summary = response.json()
    assert summary["status"] == "partial_success"
    assert summary["total_rows"] == 4
    assert summary["successful_rows"] == 2
    assert summary["failed_rows"] == 2
    assert summary["errors_url"] == f"/imports/{summary['id']}/errors"

    errors_response = client.get(summary["errors_url"])
    assert errors_response.status_code == 200
    errors = errors_response.json()
    assert errors["total"] == 2
    assert [item["error_code"] for item in errors["items"]] == [
        "invalid_email",
        "invalid_tier",
    ]

    customers = client.get("/customers", params={"partner_id": "p1"}).json()
    assert customers["total"] == 2


def test_import_updates_newer_rows_and_skips_older_rows(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,ada@x.io,Ada Lovelace,active,std,20260420,vip,original
p1,002,C1001,ada@x.io,Ada Byron,active,ent,20260421,vip,newer
p1,003,C1001,ada@x.io,Ada Old,active,pro,20260419,vip,older
"""

    response = upload_csv(client, csv_text)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"

    customers = client.get("/customers", params={"partner_id": "p1"}).json()
    assert customers["total"] == 1
    customer = customers["items"][0]
    assert customer["partner_customer_id"] == "C1001"
    assert customer["name"] == "Ada Byron"
    assert customer["tier"] == "ent"
    assert customer["note"] == "newer"
    assert customer["source_updated_at"].startswith("2026-04-21")


def test_import_missing_cid_matches_by_partner_email_and_is_idempotent(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,,kat@x.io,Katherine Johnson,active,std,20260420,space,legacy
p1,002,,kat@x.io,Katherine G Johnson,active,pro,20260422,space,renamed
"""

    first_response = upload_csv(client, csv_text)
    second_response = upload_csv(client, csv_text)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["status"] == "completed"
    assert second_response.json()["status"] == "completed"

    customers = client.get("/customers", params={"partner_id": "p1"}).json()
    assert customers["total"] == 1
    customer = customers["items"][0]
    assert customer["partner_customer_id"] is None
    assert customer["email"] == "kat@x.io"
    assert customer["name"] == "Katherine G Johnson"
    assert customer["tier"] == "pro"


def test_import_defaults_blank_tier_to_std(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1002,grace@x.io,Grace Hopper,active,,20260422,compiler,missing
"""

    response = upload_csv(client, csv_text)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"

    customers = client.get("/customers", params={"partner_id": "p1"}).json()
    assert customers["total"] == 1
    assert customers["items"][0]["tier"] == "std"


def test_import_rejects_non_csv_upload(client):
    response = upload_csv(client, "not,csv\n", filename="customers.txt")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV files are supported."


def test_import_accepts_normal_row(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email
"""

    response = upload_csv(client, csv_text)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"


def test_import_recovers_wrapped_multiline_name(client, caplog):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,Ada@x.io,Ada
Lovelace,active,ent,20260420,vip,email
"""

    response = upload_csv(client, csv_text)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    customer = client.get("/customers", params={"partner_id": "p1"}).json()["items"][0]
    assert customer["name"] == "Ada Lovelace"
    assert "customer_import_multiline_recovered" in caplog.messages


def test_import_records_unrecoverable_malformed_row(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email,unexpected
"""

    response = upload_csv(client, csv_text)

    assert response.status_code == 201
    summary = response.json()
    assert summary["status"] == "failed"
    assert summary["total_rows"] == 1
    assert summary["successful_rows"] == 0
    assert summary["failed_rows"] == 1
    errors = client.get(summary["errors_url"]).json()["items"]
    assert errors[0]["error_code"] == "invalid_column_count"


def test_example_csv_uses_newest_upd_value(client):
    csv_text = Path("tests/example.csv").read_text()

    response = upload_csv(client, csv_text, filename="example.csv")

    assert response.status_code == 201
    summary = response.json()
    assert summary["status"] == "partial_success"
    assert summary["total_rows"] == 19
    assert summary["successful_rows"] == 17
    assert summary["failed_rows"] == 2

    errors = client.get(summary["errors_url"]).json()
    assert [item["error_code"] for item in errors["items"]] == [
        "invalid_email",
        "invalid_tier",
    ]

    customers = client.get(
        "/customers",
        params={"partner_id": "p1", "page_size": 100},
    ).json()["items"]
    customers_by_cid = {
        customer["partner_customer_id"]: customer
        for customer in customers
        if customer["partner_customer_id"]
    }

    assert customers_by_cid["C1001"]["name"] == "Ada Byron"
    assert customers_by_cid["C1001"]["source_updated_at"].startswith("2026-04-21")
    assert customers_by_cid["C1002"]["tier"] == "std"
    assert customers_by_cid["C1002"]["source_updated_at"].startswith("2026-04-22")
    assert customers_by_cid["C1006"]["email"] == "eve@x.io"
    assert customers_by_cid["C1006"]["tier"] == "ent"
    assert customers_by_cid["C1006"]["source_updated_at"].startswith("2026-04-22")
