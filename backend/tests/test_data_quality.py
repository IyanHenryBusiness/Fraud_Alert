"""Tests for the pure Pandas data-quality engine (Phase 4).

These tests build small DataFrames directly and never touch SQL Server.
"""
import json
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.services.data_quality_service import (
    CUSTOMER_REFERENCE_MISMATCH_POINTS,
    DUPLICATE_BUSINESS_TRANSACTION_ID_POINTS,
    MISSING_CHANNEL_POINTS,
    MISSING_LOCATION_POINTS,
    MISSING_MERCHANT_POINTS,
    NONPOSITIVE_AMOUNT_POINTS,
    analyze_data_quality,
)

BASE_COLUMNS = [
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
]


def make_row(**overrides):
    row = {
        "transaction_id": 1,
        "customer_id": 101,
        "business_transaction_id": "BIZ-1",
        "transaction_datetime": pd.Timestamp("2026-07-01T09:00:00"),
        "recorded_customer_reference": "CUST-1001",
        "customer_reference": "CUST-1001",
        "amount": 42.50,
        "merchant_name": "Market Fresh",
        "merchant_category": "Groceries",
        "channel": "Mobile",
        "location": "Seattle, WA",
    }
    row.update(overrides)
    return row


def make_df(rows):
    return pd.DataFrame(rows, columns=BASE_COLUMNS)


def rule_names(results, transaction_id):
    return [item["rule"] for item in results[transaction_id]]


def test_normal_transaction_has_no_rules():
    df = make_df([make_row(transaction_id=1)])
    results = analyze_data_quality(df)
    assert results[1] == []


def test_duplicate_business_transaction_id_applies_to_all_matches():
    df = make_df(
        [
            make_row(transaction_id=1, business_transaction_id="BIZ-REP-9001"),
            make_row(transaction_id=2, business_transaction_id="BIZ-REP-9001"),
        ]
    )
    results = analyze_data_quality(df)
    for tid in (1, 2):
        assert rule_names(results, tid) == ["duplicate_business_transaction_id"]
        evidence = results[tid][0]["evidence"]
        assert evidence == {
            "business_transaction_id": "BIZ-REP-9001",
            "occurrence_count": 2,
        }
        assert results[tid][0]["points"] == DUPLICATE_BUSINESS_TRANSACTION_ID_POINTS


def test_missing_business_ids_are_not_treated_as_duplicates():
    df = make_df(
        [
            make_row(transaction_id=1, business_transaction_id=None),
            make_row(transaction_id=2, business_transaction_id="   "),
            make_row(transaction_id=3, business_transaction_id=""),
        ]
    )
    results = analyze_data_quality(df)
    for tid in (1, 2, 3):
        assert "duplicate_business_transaction_id" not in rule_names(results, tid)


def test_none_merchant_triggers_missing_merchant():
    df = make_df([make_row(transaction_id=1, merchant_name=None)])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["missing_merchant"]
    result = results[1][0]
    assert result["points"] == MISSING_MERCHANT_POINTS
    assert result["evidence"] == {"field": "merchant_name", "observed_value": None}


def test_whitespace_merchant_triggers_missing_merchant():
    df = make_df([make_row(transaction_id=1, merchant_name="   ")])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["missing_merchant"]


def test_missing_channel_triggers_missing_channel():
    df = make_df([make_row(transaction_id=1, channel=None)])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["missing_channel"]
    assert results[1][0]["points"] == MISSING_CHANNEL_POINTS


def test_missing_location_triggers_missing_location():
    df = make_df([make_row(transaction_id=1, location="")])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["missing_location"]
    assert results[1][0]["points"] == MISSING_LOCATION_POINTS


def test_zero_amount_triggers_nonpositive_amount():
    df = make_df([make_row(transaction_id=1, amount=0.0)])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["nonpositive_amount"]
    result = results[1][0]
    assert result["points"] == NONPOSITIVE_AMOUNT_POINTS
    assert result["evidence"] == {"amount": 0.0, "expected": "greater_than_zero"}


def test_negative_amount_triggers_nonpositive_amount():
    df = make_df([make_row(transaction_id=1, amount=Decimal("-18.20"))])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["nonpositive_amount"]


def test_positive_amount_does_not_trigger_nonpositive_amount():
    df = make_df([make_row(transaction_id=1, amount=42.50)])
    results = analyze_data_quality(df)
    assert "nonpositive_amount" not in rule_names(results, 1)


def test_numpy_integer_zero_triggers_nonpositive_amount():
    df = make_df([make_row(transaction_id=1, amount=np.int64(0))])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["nonpositive_amount"]


def test_numpy_float_negative_triggers_nonpositive_amount():
    df = make_df([make_row(transaction_id=1, amount=np.float64(-5.5))])
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["nonpositive_amount"]


def test_numpy_positive_amount_does_not_trigger_nonpositive_amount():
    df = make_df([make_row(transaction_id=1, amount=np.float64(10.5))])
    results = analyze_data_quality(df)
    assert "nonpositive_amount" not in rule_names(results, 1)


def test_differing_customer_reference_triggers_mismatch():
    df = make_df(
        [
            make_row(
                transaction_id=1,
                recorded_customer_reference="CUST-9999",
                customer_reference="CUST-1001",
            )
        ]
    )
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == ["customer_reference_mismatch"]
    result = results[1][0]
    assert result["points"] == CUSTOMER_REFERENCE_MISMATCH_POINTS
    assert result["evidence"] == {
        "recorded_customer_reference": "CUST-9999",
        "expected_customer_reference": "CUST-1001",
    }


def test_matching_references_do_not_trigger_mismatch():
    df = make_df(
        [
            make_row(
                transaction_id=1,
                recorded_customer_reference=" CUST-1001 ",
                customer_reference="CUST-1001",
            )
        ]
    )
    results = analyze_data_quality(df)
    assert "customer_reference_mismatch" not in rule_names(results, 1)


def test_missing_recorded_reference_does_not_trigger_mismatch():
    df = make_df(
        [
            make_row(
                transaction_id=1,
                recorded_customer_reference=None,
                customer_reference="CUST-1001",
            )
        ]
    )
    results = analyze_data_quality(df)
    assert "customer_reference_mismatch" not in rule_names(results, 1)


def test_multiple_rules_can_trigger_for_one_transaction():
    df = make_df(
        [
            make_row(
                transaction_id=1,
                merchant_name=None,
                channel=None,
                amount=0.0,
            )
        ]
    )
    results = analyze_data_quality(df)
    assert set(rule_names(results, 1)) == {
        "missing_merchant",
        "missing_channel",
        "nonpositive_amount",
    }


def test_rule_order_is_deterministic():
    df = make_df(
        [
            make_row(
                transaction_id=1,
                business_transaction_id="BIZ-REP-9001",
                merchant_name=None,
                channel=None,
                location=None,
                amount=0.0,
                recorded_customer_reference="CUST-9999",
                customer_reference="CUST-1001",
            ),
            make_row(transaction_id=2, business_transaction_id="BIZ-REP-9001"),
        ]
    )
    results = analyze_data_quality(df)
    assert rule_names(results, 1) == [
        "duplicate_business_transaction_id",
        "missing_merchant",
        "missing_channel",
        "missing_location",
        "nonpositive_amount",
        "customer_reference_mismatch",
    ]


def test_decimal_and_numpy_evidence_is_json_serializable():
    df = make_df(
        [
            make_row(
                transaction_id=1,
                amount=Decimal("0.00"),
            )
        ]
    )
    df["transaction_id"] = df["transaction_id"].astype(np.int64)
    results = analyze_data_quality(df)
    # Should not raise.
    serialized = json.dumps(results[1])
    assert "nonpositive_amount" in serialized


def test_missing_required_columns_raise_value_error():
    df = pd.DataFrame([{"transaction_id": 1, "amount": 10.0}])
    with pytest.raises(ValueError) as exc_info:
        analyze_data_quality(df)
    message = str(exc_info.value)
    assert "customer_id" in message
    assert "merchant_name" in message


def test_input_dataframe_is_not_modified():
    df = make_df([make_row(transaction_id=1)])
    original = df.copy(deep=True)
    analyze_data_quality(df)
    pd.testing.assert_frame_equal(df, original)
