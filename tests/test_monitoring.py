def test_health_checks_database_and_returns_request_id(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "partner-customer-import-api",
        "database": "ok",
    }
    assert response.headers["X-Request-ID"]


def test_metrics_reports_requests_and_imports(client):
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email
"""
    import_response = client.post(
        "/imports/customers",
        files={"file": ("customers.csv", csv_text, "text/csv")},
    )
    assert import_response.status_code == 201

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["imports"]["by_status"]["completed"] >= 1
    assert metrics["imports"]["rows"]["successful"] >= 1
    assert any(
        item["method"] == "POST"
        and item["path"] == "/imports/customers"
        and item["status_code"] == 201
        for item in metrics["requests"]
    )
