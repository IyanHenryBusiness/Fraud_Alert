"""Pure Pandas/Python data-quality engine (Phase 4).

This module performs deterministic data-quality checks on transaction data.
It does not connect to SQL Server, commit data, call FastAPI, or make any
fraud determination -- it only flags data-quality issues that require review.
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS: list[str] = [
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

# Rule identifiers, in the exact deterministic order they must be evaluated.
RULE_DUPLICATE_BUSINESS_TRANSACTION_ID = "duplicate_business_transaction_id"
RULE_MISSING_MERCHANT = "missing_merchant"
RULE_MISSING_CHANNEL = "missing_channel"
RULE_MISSING_LOCATION = "missing_location"
RULE_NONPOSITIVE_AMOUNT = "nonpositive_amount"
RULE_CUSTOMER_REFERENCE_MISMATCH = "customer_reference_mismatch"

# Named point constants for each rule.
DUPLICATE_BUSINESS_TRANSACTION_ID_POINTS = 20
MISSING_MERCHANT_POINTS = 10
MISSING_CHANNEL_POINTS = 5
MISSING_LOCATION_POINTS = 5
NONPOSITIVE_AMOUNT_POINTS = 25
CUSTOMER_REFERENCE_MISMATCH_POINTS = 25


def _is_blank(value: Any) -> bool:
    """Return True when value is None, NaN, empty, or whitespace-only."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_evidence_value(value: Any) -> Any:
    """Convert a raw value into a JSON-safe evidence value."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        as_float = float(value)
        return None if math.isnan(as_float) else as_float
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_transaction_id(value: Any) -> int:
    """Coerce a transaction_id value (possibly a NumPy int) into a plain int."""
    return int(value)


def _to_amount_float(value: Any) -> float | None:
    """Safely convert an amount value to float, or None if not convertible."""
    if _is_blank(value):
        return None
    if isinstance(value, (np.integer, np.floating)):
        as_float = float(value)
        return None if math.isnan(as_float) else as_float
    if isinstance(value, (int, float, Decimal)):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, str):
        try:
            return float(Decimal(value.strip()))
        except (InvalidOperation, ValueError):
            return None
    return None


def _make_result(
    rule: str, explanation: str, points: int, evidence: dict[str, Any]
) -> dict[str, Any]:
    """Build a single rule result dict with JSON-safe evidence values."""
    return {
        "rule": rule,
        "explanation": explanation,
        "points": points,
        "evidence": {key: _normalize_evidence_value(val) for key, val in evidence.items()},
    }


def analyze_data_quality(df: pd.DataFrame) -> dict[int, list[dict[str, Any]]]:
    """Run deterministic data-quality checks over transaction data.

    Args:
        df: DataFrame of transactions joined with customer data. Must contain
            all columns listed in REQUIRED_COLUMNS.

    Returns:
        Mapping of transaction_id to an ordered list of data-quality-issue
        dicts (see RULE_* constants for the fixed evaluation order). Every
        transaction_id in the input appears in the result, even with an
        empty list. This function makes no fraud determination -- it only
        flags data-quality issues that require review.

    Raises:
        ValueError: If any required column is missing from df.
    """
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"analyze_data_quality is missing required columns: {missing_columns}"
        )

    work_df = df.copy(deep=True)
    work_df = work_df.sort_values("transaction_id", kind="stable").reset_index(drop=True)

    results: dict[int, list[dict[str, Any]]] = {
        _to_transaction_id(tid): [] for tid in work_df["transaction_id"]
    }

    # Rule 1: duplicate_business_transaction_id
    stripped_ids = work_df["business_transaction_id"].apply(
        lambda v: None if _is_blank(v) else str(v).strip()
    )
    nonblank_mask = stripped_ids.notna()
    occurrence_counts = stripped_ids[nonblank_mask].value_counts()
    for idx in work_df.index[nonblank_mask]:
        biz_id = stripped_ids.loc[idx]
        count = int(occurrence_counts.loc[biz_id])
        if count > 1:
            tid = _to_transaction_id(work_df.loc[idx, "transaction_id"])
            results[tid].append(
                _make_result(
                    RULE_DUPLICATE_BUSINESS_TRANSACTION_ID,
                    "The business transaction identifier occurred more than once.",
                    DUPLICATE_BUSINESS_TRANSACTION_ID_POINTS,
                    {"business_transaction_id": biz_id, "occurrence_count": count},
                )
            )

    # Rule 2: missing_merchant
    for _, row in work_df.iterrows():
        if _is_blank(row["merchant_name"]):
            tid = _to_transaction_id(row["transaction_id"])
            results[tid].append(
                _make_result(
                    RULE_MISSING_MERCHANT,
                    "The merchant name is missing or blank and requires review.",
                    MISSING_MERCHANT_POINTS,
                    {"field": "merchant_name", "observed_value": None},
                )
            )

    # Rule 3: missing_channel
    for _, row in work_df.iterrows():
        if _is_blank(row["channel"]):
            tid = _to_transaction_id(row["transaction_id"])
            results[tid].append(
                _make_result(
                    RULE_MISSING_CHANNEL,
                    "The transaction channel is missing or blank and requires review.",
                    MISSING_CHANNEL_POINTS,
                    {"field": "channel", "observed_value": None},
                )
            )

    # Rule 4: missing_location
    for _, row in work_df.iterrows():
        if _is_blank(row["location"]):
            tid = _to_transaction_id(row["transaction_id"])
            results[tid].append(
                _make_result(
                    RULE_MISSING_LOCATION,
                    "The transaction location is missing or blank and requires review.",
                    MISSING_LOCATION_POINTS,
                    {"field": "location", "observed_value": None},
                )
            )

    # Rule 5: nonpositive_amount
    for _, row in work_df.iterrows():
        amount = _to_amount_float(row["amount"])
        if amount is not None and amount <= 0:
            tid = _to_transaction_id(row["transaction_id"])
            results[tid].append(
                _make_result(
                    RULE_NONPOSITIVE_AMOUNT,
                    "The transaction amount is not greater than zero and requires review.",
                    NONPOSITIVE_AMOUNT_POINTS,
                    {"amount": amount, "expected": "greater_than_zero"},
                )
            )

    # Rule 6: customer_reference_mismatch
    for _, row in work_df.iterrows():
        recorded = row["recorded_customer_reference"]
        if _is_blank(recorded):
            continue
        expected = row["customer_reference"]
        recorded_str = str(recorded).strip()
        expected_str = "" if _is_blank(expected) else str(expected).strip()
        if recorded_str != expected_str:
            tid = _to_transaction_id(row["transaction_id"])
            results[tid].append(
                _make_result(
                    RULE_CUSTOMER_REFERENCE_MISMATCH,
                    "The recorded customer reference does not match the customer on file "
                    "and requires review.",
                    CUSTOMER_REFERENCE_MISMATCH_POINTS,
                    {
                        "recorded_customer_reference": recorded_str,
                        "expected_customer_reference": expected_str,
                    },
                )
            )

    return results
