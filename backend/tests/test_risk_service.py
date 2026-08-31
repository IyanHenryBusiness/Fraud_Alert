"""Tests for the pure Pandas risk-analysis engine (Phase 4).

These tests build small DataFrames directly and never touch SQL Server.
"""
import json
from decimal import Decimal

import pandas as pd
import pytest

from app.services.risk_service import (
    HIGH_RISK_CUSTOMER_ACTIVITY_POINTS,
    LARGE_TRANSACTION_POINTS,
    analyze_risk,
)

COLUMNS = ["transaction_id", "customer_id", "transaction_datetime", "amount", "location"]

BASE_TIME = pd.Timestamp("2026-01-01T10:00:00")


def make_row(transaction_id, customer_id, dt, amount, location="Seattle, WA"):
    return {
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "transaction_datetime": dt,
        "amount": amount,
        "location": location,
    }


def make_df(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


def rule_names(results, transaction_id):
    return [item["rule"] for item in results[transaction_id]["rules"]]


def fake_rule(points, name="seed_rule"):
    return {
        "rule": name,
        "explanation": "Seed rule for testing.",
        "points": points,
        "evidence": {},
    }


def test_large_transaction_below_threshold_does_not_trigger():
    df = make_df([make_row(1, 101, BASE_TIME, 2999.99)])
    results = analyze_risk(df, {})
    assert "large_transaction" not in rule_names(results, 1)


def test_large_transaction_at_threshold_triggers():
    df = make_df([make_row(1, 101, BASE_TIME, 3000.00)])
    results = analyze_risk(df, {})
    assert rule_names(results, 1) == ["large_transaction"]
    result = results[1]["rules"][0]
    assert result["points"] == LARGE_TRANSACTION_POINTS
    assert result["evidence"] == {"amount": 3000.00, "threshold": 3000.00}


def test_velocity_three_transactions_within_30_minutes_triggers():
    df = make_df(
        [
            make_row(1, 101, BASE_TIME, 10.00),
            make_row(2, 101, BASE_TIME + pd.Timedelta(minutes=15), 10.00),
            make_row(3, 101, BASE_TIME + pd.Timedelta(minutes=30), 10.00),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2, 3):
        assert "rapid_velocity" in rule_names(results, tid)
        evidence = next(
            r["evidence"] for r in results[tid]["rules"] if r["rule"] == "rapid_velocity"
        )
        assert evidence["related_transaction_ids"] == [1, 2, 3]
        assert evidence["transaction_count"] == 3
        assert evidence["window_minutes"] == 30


def test_velocity_three_transactions_outside_30_minutes_does_not_trigger():
    df = make_df(
        [
            make_row(1, 101, BASE_TIME, 10.00),
            make_row(2, 101, BASE_TIME + pd.Timedelta(minutes=20), 10.00),
            make_row(3, 101, BASE_TIME + pd.Timedelta(minutes=40), 10.00),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2, 3):
        assert "rapid_velocity" not in rule_names(results, tid)


def test_velocity_different_customers_not_combined():
    df = make_df(
        [
            make_row(1, 101, BASE_TIME, 10.00),
            make_row(2, 101, BASE_TIME + pd.Timedelta(minutes=10), 10.00),
            make_row(3, 102, BASE_TIME + pd.Timedelta(minutes=20), 10.00),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2, 3):
        assert "rapid_velocity" not in rule_names(results, tid)


def test_geographic_two_locations_within_60_minutes_triggers():
    df = make_df(
        [
            make_row(1, 103, BASE_TIME, 10.00, location="Austin, TX"),
            make_row(2, 103, BASE_TIME + pd.Timedelta(minutes=60), 10.00, location="Seattle, WA"),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2):
        assert "geographic_inconsistency" in rule_names(results, tid)
        evidence = next(
            r["evidence"]
            for r in results[tid]["rules"]
            if r["rule"] == "geographic_inconsistency"
        )
        assert evidence["locations"] == ["Austin, TX", "Seattle, WA"]
        assert evidence["distinct_location_count"] == 2
        assert evidence["related_transaction_ids"] == [1, 2]
        assert evidence["window_minutes"] == 60


def test_geographic_same_location_does_not_trigger():
    df = make_df(
        [
            make_row(1, 103, BASE_TIME, 10.00, location="Austin, TX"),
            make_row(2, 103, BASE_TIME + pd.Timedelta(minutes=30), 10.00, location="Austin, TX"),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2):
        assert "geographic_inconsistency" not in rule_names(results, tid)


def test_geographic_blank_location_is_ignored():
    df = make_df(
        [
            make_row(1, 103, BASE_TIME, 10.00, location=None),
            make_row(2, 103, BASE_TIME + pd.Timedelta(minutes=30), 10.00, location="Austin, TX"),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2):
        assert "geographic_inconsistency" not in rule_names(results, tid)


def test_repeated_customer_alerts_two_positive_scores_triggers():
    df = make_df(
        [
            make_row(1, 104, BASE_TIME, 5000.00),
            make_row(2, 104, BASE_TIME + pd.Timedelta(days=5), 6000.00),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2):
        assert "repeated_customer_alerts" in rule_names(results, tid)
        evidence = next(
            r["evidence"]
            for r in results[tid]["rules"]
            if r["rule"] == "repeated_customer_alerts"
        )
        assert evidence["qualifying_transaction_count"] == 2
        assert evidence["related_transaction_ids"] == [1, 2]


def test_repeated_customer_alerts_one_positive_score_does_not_trigger():
    df = make_df(
        [
            make_row(1, 104, BASE_TIME, 5000.00),
            make_row(2, 104, BASE_TIME + pd.Timedelta(days=5), 10.00),
        ]
    )
    results = analyze_risk(df, {})
    for tid in (1, 2):
        assert "repeated_customer_alerts" not in rule_names(results, tid)


def test_combined_unusual_behavior_three_prior_rules_triggers():
    df = make_df([make_row(1, 105, BASE_TIME, 10.00)])
    initial_rules = {1: [fake_rule(10, "a"), fake_rule(10, "b"), fake_rule(10, "c")]}
    results = analyze_risk(df, initial_rules)
    assert rule_names(results, 1)[:3] == ["a", "b", "c"]
    assert "combined_unusual_behavior" in rule_names(results, 1)
    evidence = next(
        r["evidence"]
        for r in results[1]["rules"]
        if r["rule"] == "combined_unusual_behavior"
    )
    assert evidence["prior_rule_count"] == 3
    assert evidence["prior_rules"] == ["a", "b", "c"]


def test_combined_unusual_behavior_two_prior_rules_does_not_trigger():
    df = make_df([make_row(1, 105, BASE_TIME, 10.00)])
    initial_rules = {1: [fake_rule(10, "a"), fake_rule(10, "b")]}
    results = analyze_risk(df, initial_rules)
    assert "combined_unusual_behavior" not in rule_names(results, 1)


def test_high_risk_customer_activity_at_threshold_triggers():
    df = make_df([make_row(1, 106, BASE_TIME, 10.00)])
    initial_rules = {1: [fake_rule(100, "a")]}
    results = analyze_risk(df, initial_rules)
    assert "high_risk_customer_activity" in rule_names(results, 1)
    evidence = next(
        r["evidence"]
        for r in results[1]["rules"]
        if r["rule"] == "high_risk_customer_activity"
    )
    assert evidence["customer_uncapped_score"] == 100
    assert evidence["threshold"] == 100
    assert evidence["related_transaction_ids"] == [1]
    assert results[1]["rules"][-1]["points"] == HIGH_RISK_CUSTOMER_ACTIVITY_POINTS


def test_high_risk_customer_activity_below_threshold_does_not_trigger():
    df = make_df([make_row(1, 106, BASE_TIME, 10.00)])
    initial_rules = {1: [fake_rule(99, "a")]}
    results = analyze_risk(df, initial_rules)
    assert "high_risk_customer_activity" not in rule_names(results, 1)


def test_scores_above_100_are_capped():
    df = make_df([make_row(1, 106, BASE_TIME, 10.00)])
    initial_rules = {1: [fake_rule(150, "a")]}
    results = analyze_risk(df, initial_rules)
    assert results[1]["uncapped_score"] >= 150
    assert results[1]["risk_score"] == 100
    assert results[1]["severity"] == "CRITICAL"


@pytest.mark.parametrize(
    "points,expected_severity",
    [
        (0, "LOW"),
        (24, "LOW"),
        (25, "MEDIUM"),
        (49, "MEDIUM"),
        (50, "HIGH"),
        (79, "HIGH"),
        (80, "CRITICAL"),
        (100, "CRITICAL"),
    ],
)
def test_severity_boundaries(points, expected_severity):
    df = make_df([make_row(1, 107, BASE_TIME, 10.00)])
    initial_rules = {1: [fake_rule(points, "a")]} if points else {}
    results = analyze_risk(df, initial_rules)
    assert results[1]["severity"] == expected_severity


def test_result_evidence_is_json_serializable():
    df = make_df(
        [
            make_row(1, 108, BASE_TIME, Decimal("5000.00")),
        ]
    )
    results = analyze_risk(df, {})
    serialized = json.dumps(results[1])
    assert "large_transaction" in serialized


def test_input_dataframe_is_not_modified():
    df = make_df([make_row(1, 101, BASE_TIME, 10.00)])
    original = df.copy(deep=True)
    analyze_risk(df, {})
    pd.testing.assert_frame_equal(df, original)


def test_initial_rules_is_not_modified():
    df = make_df([make_row(1, 101, BASE_TIME, 3000.00)])
    initial_rules = {1: [fake_rule(10, "a")]}
    original = json.dumps(initial_rules)
    analyze_risk(df, initial_rules)
    assert json.dumps(initial_rules) == original
    assert len(initial_rules[1]) == 1


def test_output_deterministic_when_row_order_changes():
    rows = [
        make_row(1, 101, BASE_TIME, 10.00),
        make_row(2, 101, BASE_TIME + pd.Timedelta(minutes=15), 10.00),
        make_row(3, 101, BASE_TIME + pd.Timedelta(minutes=30), 10.00),
    ]
    forward_results = analyze_risk(make_df(rows), {})
    reversed_results = analyze_risk(make_df(list(reversed(rows))), {})
    assert forward_results == reversed_results


def test_missing_required_columns_raise_value_error():
    df = pd.DataFrame([{"transaction_id": 1, "amount": 10.0}])
    with pytest.raises(ValueError) as exc_info:
        analyze_risk(df, {})
    message = str(exc_info.value)
    assert "customer_id" in message
    assert "transaction_datetime" in message
