"""Tests for AnalysisService (Phase 4 batch analysis endpoint's business logic).

These tests use fakes/mocks for the repositories and DB session, so they do
not require SQL Server.
"""
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.services.analysis_service import RULESET_VERSION, AnalysisService

BASE_TIME = pd.Timestamp("2026-01-01T09:00:00")


def make_record(
    transaction_id,
    customer_id,
    amount,
    merchant_name="Market Fresh",
    channel="Mobile",
    location="Seattle, WA",
    business_transaction_id=None,
    recorded_customer_reference="CUST-1001",
    customer_reference="CUST-1001",
    dt=BASE_TIME,
):
    return {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "business_transaction_id": business_transaction_id or f"BIZ-{transaction_id}",
        "transaction_datetime": dt,
        "recorded_customer_reference": recorded_customer_reference,
        "customer_reference": customer_reference,
        "amount": amount,
        "merchant_name": merchant_name,
        "merchant_category": "Groceries",
        "channel": channel,
        "location": location,
    }


class FakeTransactionRepository:
    def __init__(self, records):
        self._records = records

    def get_transactions_for_analysis(self):
        return self._records


class FailingTransactionRepository:
    def get_transactions_for_analysis(self):
        raise RuntimeError("simulated read failure")


class FakeAlertRepository:
    def __init__(self, existing=None, add_should_fail=False):
        self.existing = existing or {}
        self.added = []
        self.updated = []
        self._add_should_fail = add_should_fail

    def get_by_analysis_key(self, analysis_key):
        return self.existing.get(analysis_key)

    def add(self, alert):
        if self._add_should_fail:
            raise RuntimeError("simulated persistence failure")
        self.added.append(alert)
        return alert

    def update_calculated_fields(
        self, alert, *, alert_type, risk_score, severity, rule_evidence, updated_at
    ):
        alert.alert_type = alert_type
        alert.risk_score = risk_score
        alert.severity = severity
        alert.rule_evidence = rule_evidence
        alert.updated_at = updated_at
        self.updated.append(alert)
        return alert


def make_existing_alert(transaction_id, customer_id, analysis_key):
    return SimpleNamespace(
        alert_id=5001,
        transaction_id=transaction_id,
        customer_id=customer_id,
        analysis_key=analysis_key,
        alert_type="LEGACY",
        risk_score=10,
        severity="LOW",
        alert_status="ACKNOWLEDGED",
        rule_evidence="[]",
        notes="Analyst reviewed this previously.",
        created_at=datetime(2026, 1, 1, 0, 0, 0),
        updated_at=datetime(2026, 1, 1, 0, 0, 0),
    )


def build_service(records, existing=None, add_should_fail=False):
    db = MagicMock()
    service = AnalysisService(db)
    service.transaction_repo = FakeTransactionRepository(records)
    service.alert_repo = FakeAlertRepository(existing=existing, add_should_fail=add_should_fail)
    return service, db


def test_empty_transaction_input_returns_zero_counts():
    service, db = build_service([])
    result = service.run()
    assert result.transactions_analyzed == 0
    assert result.alerts_created == 0
    assert result.alerts_updated == 0
    assert result.transactions_without_alerts == 0
    assert result.quality_issues_found == 0
    assert result.severity_totals.model_dump() == {
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 0,
        "CRITICAL": 0,
    }
    db.commit.assert_not_called()


def test_zero_score_transactions_are_not_persisted():
    records = [make_record(1, 101, 10.00)]
    service, db = build_service(records)
    result = service.run()
    assert result.transactions_without_alerts == 1
    assert result.alerts_created == 0
    assert service.alert_repo.added == []


def test_new_reportable_result_increments_alerts_created():
    records = [make_record(1, 101, 5000.00)]
    service, db = build_service(records)
    result = service.run()
    assert result.alerts_created == 1
    assert result.alerts_updated == 0
    assert len(service.alert_repo.added) == 1
    new_alert = service.alert_repo.added[0]
    assert new_alert.transaction_id == 1
    assert new_alert.customer_id == 101
    assert new_alert.analysis_key == "1:v1"
    assert new_alert.alert_type == "RULE_ANALYSIS"
    assert new_alert.alert_status == "OPEN"
    assert new_alert.notes is None
    assert new_alert.created_at == new_alert.updated_at


def test_existing_analysis_key_increments_alerts_updated():
    records = [make_record(1, 101, 5000.00)]
    existing_alert = make_existing_alert(1, 101, "1:v1")
    service, db = build_service(records, existing={"1:v1": existing_alert})
    result = service.run()
    assert result.alerts_updated == 1
    assert result.alerts_created == 0
    assert service.alert_repo.updated == [existing_alert]


def test_existing_alert_status_is_preserved():
    records = [make_record(1, 101, 5000.00)]
    existing_alert = make_existing_alert(1, 101, "1:v1")
    service, db = build_service(records, existing={"1:v1": existing_alert})
    service.run()
    assert existing_alert.alert_status == "ACKNOWLEDGED"


def test_existing_notes_are_preserved():
    records = [make_record(1, 101, 5000.00)]
    existing_alert = make_existing_alert(1, 101, "1:v1")
    service, db = build_service(records, existing={"1:v1": existing_alert})
    service.run()
    assert existing_alert.notes == "Analyst reviewed this previously."


def test_existing_created_at_is_preserved():
    records = [make_record(1, 101, 5000.00)]
    existing_alert = make_existing_alert(1, 101, "1:v1")
    original_created_at = existing_alert.created_at
    service, db = build_service(records, existing={"1:v1": existing_alert})
    service.run()
    assert existing_alert.created_at == original_created_at


def test_calculated_fields_are_updated():
    records = [make_record(1, 101, 5000.00)]
    existing_alert = make_existing_alert(1, 101, "1:v1")
    service, db = build_service(records, existing={"1:v1": existing_alert})
    service.run()
    assert existing_alert.alert_type == "RULE_ANALYSIS"
    assert existing_alert.risk_score > 0
    assert existing_alert.severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert json.loads(existing_alert.rule_evidence)
    assert existing_alert.updated_at > datetime(2026, 1, 1, 0, 0, 0)


def test_analysis_key_uses_transaction_id_v1_format():
    records = [make_record(42, 101, 5000.00)]
    service, db = build_service(records)
    service.run()
    assert service.alert_repo.added[0].analysis_key == f"42:{RULESET_VERSION}"


def test_rule_evidence_is_valid_serialized_json():
    records = [make_record(1, 101, 5000.00, merchant_name=None)]
    service, db = build_service(records)
    service.run()
    new_alert = service.alert_repo.added[0]
    parsed = json.loads(new_alert.rule_evidence)
    assert isinstance(parsed, list)
    for rule in parsed:
        assert {"rule", "explanation", "points", "evidence"} <= rule.keys()
        json.dumps(rule)


def test_quality_issues_found_counts_only_data_quality_rules():
    # merchant_name None -> 1 data-quality rule (missing_merchant).
    # amount also large -> triggers large_transaction risk rule, which must
    # NOT be counted in quality_issues_found.
    records = [make_record(1, 101, 5000.00, merchant_name=None)]
    service, db = build_service(records)
    result = service.run()
    assert result.quality_issues_found == 1


def test_severity_totals_always_contain_all_four_keys():
    records = [make_record(1, 101, 10.00)]
    service, db = build_service(records)
    result = service.run()
    assert set(result.severity_totals.model_dump().keys()) == {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }


def test_commit_occurs_once_on_success():
    records = [make_record(1, 101, 5000.00)]
    service, db = build_service(records)
    service.run()
    assert db.commit.call_count == 1
    db.rollback.assert_not_called()


def test_rollback_occurs_on_persistence_failure():
    records = [make_record(1, 101, 5000.00)]
    service, db = build_service(records, add_should_fail=True)
    with pytest.raises(RuntimeError):
        service.run()
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_rollback_occurs_when_reading_transactions_fails():
    db = MagicMock()
    service = AnalysisService(db)
    service.transaction_repo = FailingTransactionRepository()
    service.alert_repo = FakeAlertRepository()

    with pytest.raises(RuntimeError, match="simulated read failure"):
        service.run()

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_transaction_repository_returns_all_required_dataframe_columns():
    from app.repositories.transaction_repository import TransactionRepository

    required_columns = {
        "transaction_id",
        "customer_id",
        "business_transaction_id",
        "transaction_datetime",
        "recorded_customer_reference",
        "customer_reference",
        "amount",
        "merchant_name",
        "merchant_category",
        "channel",
        "location",
    }
    fake_row = {col: None for col in required_columns}
    fake_row.update({"transaction_id": 1, "customer_id": 101})

    db = MagicMock()
    db.execute.return_value.mappings.return_value.all.return_value = [fake_row]

    repo = TransactionRepository(db)
    results = repo.get_transactions_for_analysis()

    assert len(results) == 1
    assert required_columns <= results[0].keys()


def test_existing_alert_routes_remain_functional():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/api/transactions" in paths
    assert "/api/alerts" in paths
    assert "/api/alerts/{alert_id}" in paths
    assert "/api/alerts/{alert_id}/status" in paths
    assert "/api/analysis/run" in paths
