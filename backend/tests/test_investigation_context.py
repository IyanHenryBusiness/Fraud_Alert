"""Tests for the constrained investigation context builder (Phase 5).

These tests use plain SimpleNamespace fakes for ORM instances, so they do
not require SQL Server or network access.
"""
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.investigation_context_service import (
    CustomerAggregates,
    InvestigationContextError,
    build_investigation_context,
)


def make_alert(rule_evidence, alert_id=5001, analysis_key="1006:v0", risk_score=94, severity="CRITICAL"):
    return SimpleNamespace(
        alert_id=alert_id,
        analysis_key=analysis_key,
        risk_score=risk_score,
        severity=severity,
        rule_evidence=rule_evidence,
    )


def make_transaction(
    transaction_id=1006,
    business_transaction_id="BIZ-LARGE-3001",
    transaction_datetime=datetime(2026, 7, 4, 18, 33, 0),
    amount=Decimal("95000.00"),
    merchant_name="Luxury Auto",
    merchant_category="Automotive",
    channel="Store",
    location="New York, NY",
):
    return SimpleNamespace(
        transaction_id=transaction_id,
        business_transaction_id=business_transaction_id,
        transaction_datetime=transaction_datetime,
        amount=amount,
        merchant_name=merchant_name,
        merchant_category=merchant_category,
        channel=channel,
        location=location,
    )


def make_customer(
    customer_id=101,
    customer_reference="CUST-1001",
    first_name="Alice",
    last_name="Nguyen",
    email="alice.nguyen@example.com",
    phone="+1-206-555-0101",
    date_of_birth=datetime(1988, 4, 12),
):
    return SimpleNamespace(
        customer_id=customer_id,
        customer_reference=customer_reference,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        date_of_birth=date_of_birth,
    )


RISK_RULE_EVIDENCE = json.dumps(
    [
        {
            "rule": "large_transaction",
            "explanation": "Transaction amount met or exceeded $3,000.",
            "points": 30,
            "evidence": {"amount": 95000.00, "threshold": 3000.00},
        }
    ]
)

MIXED_RULE_EVIDENCE = json.dumps(
    [
        {
            "rule": "large_transaction",
            "explanation": "Transaction amount met or exceeded $3,000.",
            "points": 30,
            "evidence": {"amount": 95000.00, "threshold": 3000.00},
        },
        {
            "rule": "missing_merchant",
            "explanation": "The merchant name is missing or blank and requires review.",
            "points": 10,
            "evidence": {"field": "merchant_name", "observed_value": None},
        },
        {
            "rule": "customer_reference_mismatch",
            "explanation": "The recorded customer reference does not match the customer on file.",
            "points": 25,
            "evidence": {
                "recorded_customer_reference": "CUST-9999",
                "expected_customer_reference": "CUST-1001",
            },
        },
    ]
)


def build_context(rule_evidence=RISK_RULE_EVIDENCE, **alert_kwargs):
    alert = make_alert(rule_evidence, **alert_kwargs)
    transaction = make_transaction()
    customer = make_customer()
    aggregates = CustomerAggregates(transaction_count=10, alert_count=3, max_risk_score=94)
    return build_investigation_context(
        alert=alert, transaction=transaction, customer=customer, aggregates=aggregates
    )


def test_context_includes_only_selected_evidence():
    context = build_context()
    assert context["alert_id"] == 5001
    assert context["analysis_key"] == "1006:v0"
    assert context["calculated_risk_score"] == 94
    assert context["severity"] == "CRITICAL"
    assert context["transaction"]["transaction_id"] == 1006
    assert context["transaction"]["business_transaction_id"] == "BIZ-LARGE-3001"
    assert context["customer"]["customer_reference"] == "CUST-1001"
    assert context["customer"]["transaction_count"] == 10
    assert context["customer"]["alert_count"] == 3
    assert context["customer"]["max_risk_score"] == 94


def test_context_excludes_customer_pii():
    context = build_context()
    serialized = json.dumps(context)
    assert "first_name" not in context["customer"]
    assert "last_name" not in context["customer"]
    assert "email" not in context["customer"]
    assert "phone" not in context["customer"]
    assert "date_of_birth" not in context["customer"]
    assert "Alice" not in serialized
    assert "Nguyen" not in serialized
    assert "alice.nguyen@example.com" not in serialized
    assert "+1-206-555-0101" not in serialized
    assert "1988-04-12" not in serialized


def test_decimal_and_datetime_are_json_serializable():
    context = build_context()
    serialized = json.dumps(context)  # must not raise
    reloaded = json.loads(serialized)
    assert reloaded["transaction"]["amount"] == 95000.00
    assert isinstance(reloaded["transaction"]["amount"], float)
    assert reloaded["transaction"]["transaction_datetime"] == "2026-07-04T18:33:00"


def test_rules_are_split_into_triggered_and_data_quality():
    context = build_context(rule_evidence=MIXED_RULE_EVIDENCE)
    triggered_rule_names = {rule["rule"] for rule in context["triggered_rules"]}
    data_quality_rule_names = {rule["rule"] for rule in context["data_quality_issues"]}
    assert triggered_rule_names == {"large_transaction"}
    assert data_quality_rule_names == {"missing_merchant", "customer_reference_mismatch"}


@pytest.mark.parametrize(
    "malformed_evidence",
    [
        "not json at all {",
        json.dumps({"rule": "large_transaction"}),  # not a list
        json.dumps([{"explanation": "missing the rule key"}]),
        json.dumps(["not-a-dict"]),
    ],
)
def test_malformed_rule_evidence_raises_controlled_error(malformed_evidence):
    with pytest.raises(InvestigationContextError):
        build_context(rule_evidence=malformed_evidence)
