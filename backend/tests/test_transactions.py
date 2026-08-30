from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_get_transactions_returns_records():
    response = client.get("/api/transactions?limit=5&offset=0")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
    assert payload["count"] == len(payload["items"])
    assert payload["count"] > 0

    first = payload["items"][0]
    assert "transaction_id" in first
    assert "customer" in first
    assert "customer_id" in first["customer"]
