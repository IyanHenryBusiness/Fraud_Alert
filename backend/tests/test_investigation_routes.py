"""Tests for the Phase 5 investigation routes.

These tests override the get_db dependency and patch InvestigationService,
so they do not require SQL Server or network access.
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.schemas.investigation import InvestigationResponse
from app.services.investigation_service import AlertNotFoundError, InvestigationGenerationError

client = TestClient(app)


def _override_get_db():
    yield MagicMock()


@pytest.fixture(autouse=True)
def override_db_dependency():
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def make_response(alert_id=5001):
    return InvestigationResponse(
        investigation_id=10000,
        alert_id=alert_id,
        provider="mock",
        summary="Alert flagged for analyst review.",
        risk_factors=["large_transaction: Transaction amount met or exceeded $3,000."],
        missing_information=[],
        recommended_actions=[
            {
                "priority": 1,
                "action": "Review the triggered risk rules with the analyst team.",
                "reason": "1 risk rule(s) were triggered for this alert.",
            }
        ],
        disclaimer=(
            "This result supports analyst review and does not establish that "
            "fraud occurred."
        ),
        created_at=datetime(2026, 7, 15, 0, 0, 0),
    )


def test_generate_investigation_success(monkeypatch):
    monkeypatch.setattr(
        "app.routes.investigations.InvestigationService.generate",
        lambda self, alert_id: make_response(alert_id),
    )
    response = client.post("/api/investigations/generate", json={"alert_id": 5001})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["investigation_id"] == 10000
    assert payload["alert_id"] == 5001
    assert payload["provider"] == "mock"


def test_generate_investigation_unknown_alert_returns_404(monkeypatch):
    def raise_not_found(self, alert_id):
        raise AlertNotFoundError(f"Alert {alert_id} not found")

    monkeypatch.setattr(
        "app.routes.investigations.InvestigationService.generate", raise_not_found
    )
    response = client.post("/api/investigations/generate", json={"alert_id": 9999})
    assert response.status_code == 404


def test_generate_investigation_invalid_request_returns_422():
    response = client.post("/api/investigations/generate", json={"alert_id": -1})
    assert response.status_code == 422

    response = client.post("/api/investigations/generate", json={})
    assert response.status_code == 422


def test_generate_investigation_generation_failure_returns_500(monkeypatch):
    def raise_generation_error(self, alert_id):
        raise InvestigationGenerationError("boom")

    monkeypatch.setattr(
        "app.routes.investigations.InvestigationService.generate",
        raise_generation_error,
    )
    response = client.post("/api/investigations/generate", json={"alert_id": 5001})
    assert response.status_code == 500
    assert "boom" not in response.text


def test_generate_investigation_route_is_registered():
    paths = app.openapi()["paths"]
    assert "/api/investigations/generate" in paths


def test_existing_phase4_routes_remain_registered():
    paths = app.openapi()["paths"]
    assert "/api/transactions" in paths
    assert "/api/alerts" in paths
    assert "/api/alerts/{alert_id}" in paths
    assert "/api/analysis/run" in paths
    assert "/health" in paths
