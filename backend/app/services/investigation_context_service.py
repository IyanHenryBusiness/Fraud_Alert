"""Builds a constrained, JSON-serializable investigation context (Phase 5).

This module performs no I/O and makes no fraud determination. It only shapes
already-retrieved ORM data into a bounded dict suitable for handing to a
Copilot-style provider. Customer PII, credentials, connection strings,
environment variables, complete tables, and unrelated transactions are
excluded by construction -- only the fields listed below are copied in.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# Rules that describe data-quality problems rather than fraud-risk signals.
DATA_QUALITY_RULES = {
    "duplicate_business_transaction_id",
    "missing_merchant",
    "missing_channel",
    "missing_location",
    "nonpositive_amount",
    "customer_reference_mismatch",
}


class InvestigationContextError(Exception):
    """Raised when a risk alert's rule_evidence cannot be parsed or is malformed."""


@dataclass(frozen=True)
class CustomerAggregates:
    """Limited, non-identifying aggregates about a customer's activity."""

    transaction_count: int
    alert_count: int
    max_risk_score: int


def _json_safe(value: Any) -> Any:
    """Recursively convert Decimal/datetime values into JSON-safe primitives."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _parse_rule_evidence(alert_id: int, rule_evidence: str) -> list[dict[str, Any]]:
    """Parse and validate a RiskAlert's rule_evidence JSON string."""
    try:
        parsed = json.loads(rule_evidence)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvestigationContextError(
            f"Alert {alert_id} has malformed rule_evidence."
        ) from exc

    if not isinstance(parsed, list):
        raise InvestigationContextError(
            f"Alert {alert_id} rule_evidence must be a JSON array."
        )

    for entry in parsed:
        if not isinstance(entry, dict) or "rule" not in entry:
            raise InvestigationContextError(
                f"Alert {alert_id} rule_evidence contains a malformed entry."
            )

    return parsed


def build_investigation_context(
    *,
    alert: Any,
    transaction: Any,
    customer: Any,
    aggregates: CustomerAggregates,
) -> dict[str, Any]:
    """Build a constrained, JSON-serializable investigation context.

    Args:
        alert: The selected RiskAlert ORM instance.
        transaction: The Transaction ORM instance linked to the alert.
        customer: The Customer ORM instance linked to the alert.
        aggregates: Limited customer-level aggregates (never full tables).

    Returns:
        A dict containing only alert_id, analysis_key, selected transaction
        facts, customer_reference, limited customer aggregates, triggered
        rules, data-quality issues, calculated risk score, and severity.

    Raises:
        InvestigationContextError: If alert.rule_evidence is not a valid
            JSON array of rule objects.
    """
    rules = _parse_rule_evidence(alert.alert_id, alert.rule_evidence)

    triggered_rules: list[dict[str, Any]] = []
    data_quality_issues: list[dict[str, Any]] = []
    for rule in rules:
        safe_rule = _json_safe(rule)
        if rule.get("rule") in DATA_QUALITY_RULES:
            data_quality_issues.append(safe_rule)
        else:
            triggered_rules.append(safe_rule)

    context: dict[str, Any] = {
        "alert_id": alert.alert_id,
        "analysis_key": alert.analysis_key,
        "calculated_risk_score": alert.risk_score,
        "severity": alert.severity,
        "transaction": {
            "transaction_id": transaction.transaction_id,
            "business_transaction_id": transaction.business_transaction_id,
            "transaction_datetime": _json_safe(transaction.transaction_datetime),
            "amount": _json_safe(transaction.amount),
            "merchant_name": transaction.merchant_name,
            "merchant_category": transaction.merchant_category,
            "channel": transaction.channel,
            "location": transaction.location,
        },
        "customer": {
            "customer_reference": customer.customer_reference,
            "transaction_count": aggregates.transaction_count,
            "alert_count": aggregates.alert_count,
            "max_risk_score": aggregates.max_risk_score,
        },
        "triggered_rules": triggered_rules,
        "data_quality_issues": data_quality_issues,
    }

    # Fail fast if an unexpected value slipped in that json.dumps cannot handle.
    json.dumps(context)
    return context
