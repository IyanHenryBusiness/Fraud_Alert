"""Pure Pandas/Python risk-analysis engine (Phase 4).

This module scores transactions using deterministic rules layered on top of
the data-quality results produced by ``data_quality_service.analyze_data_quality``.
It does not connect to SQL Server, commit data, call FastAPI, or declare that
fraud occurred -- it only produces a risk score and severity that require
review.
"""
from __future__ import annotations

import copy
import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS: list[str] = [
    "transaction_id",
    "customer_id",
    "transaction_datetime",
    "amount",
    "location",
]

# Rule identifiers, in the exact deterministic order they must be evaluated.
RULE_LARGE_TRANSACTION = "large_transaction"
RULE_RAPID_VELOCITY = "rapid_velocity"
RULE_GEOGRAPHIC_INCONSISTENCY = "geographic_inconsistency"
RULE_REPEATED_CUSTOMER_ALERTS = "repeated_customer_alerts"
RULE_COMBINED_UNUSUAL_BEHAVIOR = "combined_unusual_behavior"
RULE_HIGH_RISK_CUSTOMER_ACTIVITY = "high_risk_customer_activity"

# Named point constants for each rule.
LARGE_TRANSACTION_POINTS = 30
RAPID_VELOCITY_POINTS = 25
GEOGRAPHIC_INCONSISTENCY_POINTS = 25
REPEATED_CUSTOMER_ALERTS_POINTS = 15
COMBINED_UNUSUAL_BEHAVIOR_POINTS = 15
HIGH_RISK_CUSTOMER_ACTIVITY_POINTS = 20

# Named rule thresholds.
LARGE_TRANSACTION_THRESHOLD = 3000.00
RAPID_VELOCITY_WINDOW_MINUTES = 30
RAPID_VELOCITY_MIN_COUNT = 3
GEOGRAPHIC_WINDOW_MINUTES = 60
GEOGRAPHIC_MIN_DISTINCT_LOCATIONS = 2
REPEATED_ALERTS_MIN_COUNT = 2
COMBINED_UNUSUAL_MIN_PRIOR_RULES = 3
HIGH_RISK_CUSTOMER_THRESHOLD = 100

# Scoring constants.
RISK_SCORE_CAP = 100
SEVERITY_LOW_MAX = 24
SEVERITY_MEDIUM_MAX = 49
SEVERITY_HIGH_MAX = 79
SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"


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
    if isinstance(value, (list, tuple)):
        return [_normalize_evidence_value(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


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


def _score(rules: list[dict[str, Any]]) -> int:
    """Sum the points of every rule currently applied to a transaction."""
    return sum(rule["points"] for rule in rules)


def _severity(risk_score: int) -> str:
    """Map a capped risk score to its uppercase severity band."""
    if risk_score <= SEVERITY_LOW_MAX:
        return SEVERITY_LOW
    if risk_score <= SEVERITY_MEDIUM_MAX:
        return SEVERITY_MEDIUM
    if risk_score <= SEVERITY_HIGH_MAX:
        return SEVERITY_HIGH
    return SEVERITY_CRITICAL


def _rolling_windows(times: list[pd.Timestamp], window_minutes: int) -> list[tuple[int, int]]:
    """Return the maximal (start, end) index range within window_minutes of each start."""
    delta = pd.Timedelta(minutes=window_minutes)
    n = len(times)
    windows: list[tuple[int, int]] = []
    for i in range(n):
        j = i
        while j + 1 < n and times[j + 1] - times[i] <= delta:
            j += 1
        windows.append((i, j))
    return windows


def _build_customer_time_groups(
    sorted_df: pd.DataFrame,
) -> dict[int, list[tuple[int, pd.Timestamp, str | None]]]:
    """Group (transaction_id, timestamp, location) tuples by customer for rows with a valid timestamp."""
    valid_df = sorted_df[sorted_df["parsed_dt"].notna()]
    groups: dict[int, list[tuple[int, pd.Timestamp, str | None]]] = defaultdict(list)
    for row in valid_df.itertuples(index=False):
        customer_id = int(row.customer_id)
        groups[customer_id].append((int(row.transaction_id), row.parsed_dt, row.parsed_location))
    return groups


def _apply_large_transaction(
    sorted_df: pd.DataFrame, rules_state: dict[int, list[dict[str, Any]]]
) -> None:
    for row in sorted_df.itertuples(index=False):
        amount = row.parsed_amount
        if amount is not None and amount >= LARGE_TRANSACTION_THRESHOLD:
            tid = int(row.transaction_id)
            rules_state[tid].append(
                _make_result(
                    RULE_LARGE_TRANSACTION,
                    "Transaction amount met or exceeded $3,000.",
                    LARGE_TRANSACTION_POINTS,
                    {"amount": amount, "threshold": LARGE_TRANSACTION_THRESHOLD},
                )
            )


def _apply_rapid_velocity(
    customer_groups: dict[int, list[tuple[int, pd.Timestamp, str | None]]],
    rules_state: dict[int, list[dict[str, Any]]],
) -> None:
    for customer_id in sorted(customer_groups):
        group = customer_groups[customer_id]
        ids = [item[0] for item in group]
        times = [item[1] for item in group]
        related_by_tid: dict[int, set[int]] = defaultdict(set)
        for start, end in _rolling_windows(times, RAPID_VELOCITY_WINDOW_MINUTES):
            if end - start + 1 >= RAPID_VELOCITY_MIN_COUNT:
                window_ids = ids[start : end + 1]
                for tid in window_ids:
                    related_by_tid[tid].update(window_ids)
        for tid in sorted(related_by_tid):
            related_sorted = sorted(related_by_tid[tid])
            rules_state[tid].append(
                _make_result(
                    RULE_RAPID_VELOCITY,
                    "The customer had at least three transactions within a short rolling time window.",
                    RAPID_VELOCITY_POINTS,
                    {
                        "customer_id": customer_id,
                        "window_minutes": RAPID_VELOCITY_WINDOW_MINUTES,
                        "transaction_count": len(related_sorted),
                        "related_transaction_ids": related_sorted,
                    },
                )
            )


def _apply_geographic_inconsistency(
    customer_groups: dict[int, list[tuple[int, pd.Timestamp, str | None]]],
    rules_state: dict[int, list[dict[str, Any]]],
) -> None:
    for customer_id in sorted(customer_groups):
        group = customer_groups[customer_id]
        ids = [item[0] for item in group]
        times = [item[1] for item in group]
        locations = [item[2] for item in group]
        related_by_tid: dict[int, set[int]] = defaultdict(set)
        locations_by_tid: dict[int, set[str]] = defaultdict(set)
        for start, end in _rolling_windows(times, GEOGRAPHIC_WINDOW_MINUTES):
            window_locations = {
                loc for loc in locations[start : end + 1] if not _is_blank(loc)
            }
            if len(window_locations) >= GEOGRAPHIC_MIN_DISTINCT_LOCATIONS:
                window_ids = ids[start : end + 1]
                for tid in window_ids:
                    related_by_tid[tid].update(window_ids)
                    locations_by_tid[tid].update(window_locations)
        for tid in sorted(related_by_tid):
            related_sorted = sorted(related_by_tid[tid])
            locations_sorted = sorted(locations_by_tid[tid])
            rules_state[tid].append(
                _make_result(
                    RULE_GEOGRAPHIC_INCONSISTENCY,
                    "The customer had transactions from multiple locations within a short rolling time window.",
                    GEOGRAPHIC_INCONSISTENCY_POINTS,
                    {
                        "customer_id": customer_id,
                        "window_minutes": GEOGRAPHIC_WINDOW_MINUTES,
                        "distinct_location_count": len(locations_sorted),
                        "locations": locations_sorted,
                        "related_transaction_ids": related_sorted,
                    },
                )
            )


def _apply_repeated_customer_alerts(
    all_tids: list[int],
    customer_id_map: dict[int, int],
    rules_state: dict[int, list[dict[str, Any]]],
) -> None:
    customer_positive: dict[int, list[int]] = defaultdict(list)
    for tid in sorted(all_tids):
        if _score(rules_state[tid]) > 0:
            customer_positive[customer_id_map[tid]].append(tid)
    for customer_id in sorted(customer_positive):
        related_sorted = sorted(customer_positive[customer_id])
        if len(related_sorted) >= REPEATED_ALERTS_MIN_COUNT:
            for tid in related_sorted:
                rules_state[tid].append(
                    _make_result(
                        RULE_REPEATED_CUSTOMER_ALERTS,
                        "The customer has multiple transactions flagged for review in this batch.",
                        REPEATED_CUSTOMER_ALERTS_POINTS,
                        {
                            "customer_id": customer_id,
                            "qualifying_transaction_count": len(related_sorted),
                            "related_transaction_ids": related_sorted,
                        },
                    )
                )


def _apply_combined_unusual_behavior(
    all_tids: list[int], rules_state: dict[int, list[dict[str, Any]]]
) -> None:
    for tid in sorted(all_tids):
        current_rules = rules_state[tid]
        if len(current_rules) >= COMBINED_UNUSUAL_MIN_PRIOR_RULES:
            prior_rules = [rule["rule"] for rule in current_rules]
            rules_state[tid].append(
                _make_result(
                    RULE_COMBINED_UNUSUAL_BEHAVIOR,
                    "The transaction accumulated multiple data-quality or risk indicators.",
                    COMBINED_UNUSUAL_BEHAVIOR_POINTS,
                    {
                        "prior_rule_count": len(prior_rules),
                        "prior_rules": prior_rules,
                    },
                )
            )


def _apply_high_risk_customer_activity(
    all_tids: list[int],
    customer_id_map: dict[int, int],
    rules_state: dict[int, list[dict[str, Any]]],
) -> None:
    customer_totals: dict[int, int] = defaultdict(int)
    customer_positive: dict[int, list[int]] = defaultdict(list)
    for tid in sorted(all_tids):
        score = _score(rules_state[tid])
        if score > 0:
            customer_id = customer_id_map[tid]
            customer_totals[customer_id] += score
            customer_positive[customer_id].append(tid)
    for customer_id in sorted(customer_positive):
        total = customer_totals[customer_id]
        if total >= HIGH_RISK_CUSTOMER_THRESHOLD:
            related_sorted = sorted(customer_positive[customer_id])
            for tid in related_sorted:
                rules_state[tid].append(
                    _make_result(
                        RULE_HIGH_RISK_CUSTOMER_ACTIVITY,
                        "The customer's cumulative activity in this batch requires review.",
                        HIGH_RISK_CUSTOMER_ACTIVITY_POINTS,
                        {
                            "customer_id": customer_id,
                            "customer_uncapped_score": total,
                            "threshold": HIGH_RISK_CUSTOMER_THRESHOLD,
                            "related_transaction_ids": related_sorted,
                        },
                    )
                )


def analyze_risk(
    df: pd.DataFrame, initial_rules: dict[int, list[dict[str, Any]]]
) -> dict[int, dict[str, Any]]:
    """Score transactions using deterministic risk rules staged on data-quality results.

    Args:
        df: DataFrame of transactions. Must contain all columns listed in
            REQUIRED_COLUMNS.
        initial_rules: Mapping of transaction_id to the data-quality rule
            list produced by ``analyze_data_quality``. Not mutated.

    Returns:
        Mapping of transaction_id to a dict with "rules", "uncapped_score",
        "risk_score", and "severity". Every transaction_id in df appears in
        the result. This function makes no fraud determination -- it only
        produces a risk score and severity that require review.

    Raises:
        ValueError: If any required column is missing from df.
    """
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"analyze_risk is missing required columns: {missing_columns}")

    work_df = df.copy(deep=True)
    work_df["parsed_dt"] = pd.to_datetime(work_df["transaction_datetime"], errors="coerce")
    work_df["parsed_amount"] = work_df["amount"].apply(_to_amount_float)
    work_df["parsed_location"] = work_df["location"].apply(
        lambda v: None if _is_blank(v) else str(v).strip()
    ).astype(object)
    sorted_df = work_df.sort_values(
        ["customer_id", "parsed_dt", "transaction_id"], kind="stable", na_position="last"
    ).reset_index(drop=True)

    all_tids = [int(tid) for tid in sorted_df["transaction_id"].unique()]
    customer_id_map: dict[int, int] = {
        int(row.transaction_id): int(row.customer_id)
        for row in sorted_df.itertuples(index=False)
    }

    rules_state: dict[int, list[dict[str, Any]]] = {
        tid: [copy.deepcopy(rule) for rule in initial_rules.get(tid, [])] for tid in all_tids
    }

    customer_groups = _build_customer_time_groups(sorted_df)

    _apply_large_transaction(sorted_df, rules_state)
    _apply_rapid_velocity(customer_groups, rules_state)
    _apply_geographic_inconsistency(customer_groups, rules_state)
    _apply_repeated_customer_alerts(all_tids, customer_id_map, rules_state)
    _apply_combined_unusual_behavior(all_tids, rules_state)
    _apply_high_risk_customer_activity(all_tids, customer_id_map, rules_state)

    results: dict[int, dict[str, Any]] = {}
    for tid in sorted(all_tids):
        rules = rules_state[tid]
        uncapped_score = _score(rules)
        risk_score = min(uncapped_score, RISK_SCORE_CAP)
        results[tid] = {
            "rules": rules,
            "uncapped_score": uncapped_score,
            "risk_score": risk_score,
            "severity": _severity(risk_score),
        }
    return results
