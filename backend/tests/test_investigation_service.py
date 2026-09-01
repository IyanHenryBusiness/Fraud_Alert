"""Tests for InvestigationService (Phase 5 mock investigation generation).

These tests use fakes/mocks for the repository, DB session, and provider, so
they do not require SQL Server or network access.
"""
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.schemas.investigation import ProviderInvestigationResult, RecommendedAction
from app.services.investigation_context_service import InvestigationContextError
from app.services.investigation_service import (
    AlertNotFoundError,
    InvestigationGenerationError,
    InvestigationService,
)

RULE_EVIDENCE = json.dumps(
    [
        {
            "rule": "large_transaction",
            "explanation": "Transaction amount met or exceeded $3,000.",
            "points": 30,
            "evidence": {"amount": 95000.00, "threshold": 3000.00},
        }
    ]
)


def make_transaction():
    return SimpleNamespace(
        transaction_id=1006,
        business_transaction_id="BIZ-LARGE-3001",
        transaction_datetime=datetime(2026, 7, 4, 18, 33, 0),
        amount=Decimal("95000.00"),
        merchant_name="Luxury Auto",
        merchant_category="Automotive",
        channel="Store",
        location="New York, NY",
    )


def make_customer():
    return SimpleNamespace(
        customer_id=101,
        customer_reference="CUST-1001",
        first_name="Alice",
        last_name="Nguyen",
        email="alice.nguyen@example.com",
        phone="+1-206-555-0101",
    )


def make_alert(rule_evidence=RULE_EVIDENCE, severity="CRITICAL"):
    alert = SimpleNamespace(
        alert_id=5001,
        analysis_key="1006:v0",
        risk_score=94,
        severity=severity,
        customer_id=101,
        rule_evidence=rule_evidence,
        transaction=make_transaction(),
        customer=make_customer(),
    )
    return alert


class FakeInvestigationRepository:
    def __init__(self, alert=None, add_should_fail=False):
        self.alert = alert
        self.added = []
        self._add_should_fail = add_should_fail

    def get_alert_with_relations(self, alert_id):
        if self.alert is not None and self.alert.alert_id == alert_id:
            return self.alert
        return None

    def get_customer_transaction_count(self, customer_id):
        return 10

    def get_customer_alert_count(self, customer_id):
        return 3

    def get_customer_max_risk_score(self, customer_id):
        return 94

    def add(self, investigation):
        if self._add_should_fail:
            raise RuntimeError("simulated persistence failure")
        investigation.investigation_id = 10000
        self.added.append(investigation)
        return investigation


class FakeProvider:
    def __init__(self, result=None, should_fail=False):
        self._result = result or ProviderInvestigationResult(
            provider="mock",
            summary="Alert 5001 flagged 1 risk rule(s) for analyst review.",
            risk_factors=["large_transaction: Transaction amount met or exceeded $3,000."],
            missing_information=[],
            recommended_actions=[
                RecommendedAction(
                    priority=1,
                    action="Review the triggered risk rules with the analyst team.",
                    reason="1 risk rule(s) were triggered for this alert.",
                )
            ],
            disclaimer=(
                "This result supports analyst review and does not establish that "
                "fraud occurred."
            ),
        )
        self._should_fail = should_fail
        self.calls = []

    def generate(self, context):
        self.calls.append(context)
        if self._should_fail:
            raise RuntimeError("simulated provider failure")
        return self._result


def build_service(alert=None, add_should_fail=False, provider=None):
    db = MagicMock()

    def refresh(instance):
        instance.created_at = datetime(2026, 7, 15, 0, 0, 0)
        instance.updated_at = instance.created_at

    db.refresh.side_effect = refresh

    provider = provider or FakeProvider()
    service = InvestigationService(db, provider=provider)
    service.repo = FakeInvestigationRepository(alert=alert, add_should_fail=add_should_fail)
    return service, db, provider


def test_unknown_alert_raises_not_found():
    service, db, provider = build_service(alert=None)
    with pytest.raises(AlertNotFoundError):
        service.generate(9999)
    db.commit.assert_not_called()


def test_successful_generation_commits_once():
    alert = make_alert()
    service, db, provider = build_service(alert=alert)
    response = service.generate(5001)
    assert response.investigation_id == 10000
    assert response.alert_id == 5001
    assert response.provider == "mock"
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_context_and_response_persisted_as_valid_json():
    alert = make_alert()
    service, db, provider = build_service(alert=alert)
    service.generate(5001)
    stored = service.repo.added[0]
    json.loads(stored.context_snapshot)  # must not raise
    json.loads(stored.response_payload)  # must not raise
    assert stored.provider == "mock"
    assert stored.investigation_status == "NEW"
    assert stored.priority == "CRITICAL"
    assert stored.assigned_to is None


def test_second_request_may_create_another_investigation():
    alert = make_alert()
    service, db, provider = build_service(alert=alert)
    service.generate(5001)
    service.generate(5001)
    assert len(service.repo.added) == 2


def test_malformed_evidence_rolls_back_and_raises_controlled_error():
    alert = make_alert(rule_evidence="not json {")
    service, db, provider = build_service(alert=alert)
    with pytest.raises(InvestigationGenerationError):
        service.generate(5001)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_persistence_failure_rolls_back_and_raises_controlled_error():
    alert = make_alert()
    service, db, provider = build_service(alert=alert, add_should_fail=True)
    with pytest.raises(InvestigationGenerationError):
        service.generate(5001)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_provider_failure_rolls_back_and_raises_controlled_error():
    alert = make_alert()
    failing_provider = FakeProvider(should_fail=True)
    service, db, provider = build_service(alert=alert, provider=failing_provider)
    with pytest.raises(InvestigationGenerationError):
        service.generate(5001)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_commit_failure_rolls_back_and_hides_raw_exception():
    alert = make_alert()
    service, db, provider = build_service(alert=alert)
    db.commit.side_effect = RuntimeError("connection reset by peer")

    with pytest.raises(InvestigationGenerationError) as exc_info:
        service.generate(5001)

    db.commit.assert_called_once()
    db.rollback.assert_called_once()
    assert "connection reset by peer" not in str(exc_info.value)
