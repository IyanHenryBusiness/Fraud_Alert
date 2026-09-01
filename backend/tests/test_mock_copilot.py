"""Tests for the deterministic mock Copilot provider (Phase 5).

These tests perform no HTTP or network calls and do not require SQL Server.
"""
import copy

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas.investigation import ProviderInvestigationResult, RecommendedAction
from app.services.copilot_service import (
    DISCLAIMER,
    DeterministicMockCopilotProvider,
    get_copilot_provider,
)

SAMPLE_CONTEXT = {
    "alert_id": 5001,
    "analysis_key": "1006:v0",
    "calculated_risk_score": 94,
    "severity": "CRITICAL",
    "transaction": {
        "transaction_id": 1006,
        "business_transaction_id": "BIZ-LARGE-3001",
        "transaction_datetime": "2026-07-04T18:33:00",
        "amount": 95000.00,
        "merchant_name": "Luxury Auto",
        "merchant_category": "Automotive",
        "channel": "Store",
        "location": "New York, NY",
    },
    "customer": {
        "customer_reference": "CUST-1001",
        "transaction_count": 10,
        "alert_count": 3,
        "max_risk_score": 94,
    },
    "triggered_rules": [
        {
            "rule": "large_transaction",
            "explanation": "Transaction amount met or exceeded $3,000.",
            "points": 30,
            "evidence": {"amount": 95000.00, "threshold": 3000.00},
        }
    ],
    "data_quality_issues": [
        {
            "rule": "missing_merchant",
            "explanation": "The merchant name is missing or blank and requires review.",
            "points": 10,
            "evidence": {"field": "merchant_name", "observed_value": None},
        }
    ],
}


def test_mock_result_validates_against_schema():
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    assert isinstance(result, ProviderInvestigationResult)
    # Re-validate through the schema explicitly.
    ProviderInvestigationResult.model_validate(result.model_dump())


def test_identical_context_produces_identical_result():
    provider = DeterministicMockCopilotProvider()
    first = provider.generate(SAMPLE_CONTEXT)
    second = provider.generate(SAMPLE_CONTEXT)
    assert first.model_dump() == second.model_dump()


def test_provider_is_mock():
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    assert result.provider == "mock"


def test_disclaimer_is_exact():
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    assert result.disclaimer == DISCLAIMER
    assert (
        result.disclaimer
        == "This result supports analyst review and does not establish that fraud occurred."
    )


def test_recommended_priorities_start_at_one_and_are_consecutive():
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    priorities = [action.priority for action in result.recommended_actions]
    assert priorities == list(range(1, len(priorities) + 1))


def test_no_fraud_claim_in_summary():
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    lowered = result.summary.lower()
    assert "fraud occurred" not in lowered
    assert "is fraud" not in lowered


def test_mock_mode_performs_no_http_requests(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Mock provider must not perform HTTP requests")

    monkeypatch.setattr("socket.socket.connect", fail_if_called, raising=True)

    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    assert result.provider == "mock"


def test_factory_returns_mock_provider_for_mock_mode():
    settings = Settings(DATABASE_URL="mssql+pyodbc://unused", COPILOT_MODE="mock")
    provider = get_copilot_provider(settings)
    assert isinstance(provider, DeterministicMockCopilotProvider)


def test_factory_never_labels_mock_output_as_copilot_studio():
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(SAMPLE_CONTEXT)
    assert result.provider != "copilot_studio"


# --- Correction 1: nonblank string validation -------------------------------


BLANK_VALUES = ["", "   ", "\t\n"]


@pytest.mark.parametrize("blank_value", BLANK_VALUES)
def test_recommended_action_rejects_blank_action_and_reason(blank_value):
    with pytest.raises(ValidationError):
        RecommendedAction(priority=1, action=blank_value, reason="valid reason")
    with pytest.raises(ValidationError):
        RecommendedAction(priority=1, action="valid action", reason=blank_value)


def _valid_provider_kwargs():
    return dict(
        provider="mock",
        summary="A valid summary.",
        risk_factors=["a risk factor"],
        missing_information=[],
        recommended_actions=[
            RecommendedAction(priority=1, action="Do something.", reason="Because evidence.")
        ],
        disclaimer=DISCLAIMER,
    )


@pytest.mark.parametrize("blank_value", BLANK_VALUES)
def test_provider_result_rejects_blank_summary_and_disclaimer(blank_value):
    with pytest.raises(ValidationError):
        ProviderInvestigationResult(**{**_valid_provider_kwargs(), "summary": blank_value})
    with pytest.raises(ValidationError):
        ProviderInvestigationResult(**{**_valid_provider_kwargs(), "disclaimer": blank_value})


@pytest.mark.parametrize("blank_value", ["", "   "])
def test_provider_result_rejects_blank_list_items(blank_value):
    with pytest.raises(ValidationError):
        ProviderInvestigationResult(
            **{**_valid_provider_kwargs(), "risk_factors": [blank_value]}
        )
    with pytest.raises(ValidationError):
        ProviderInvestigationResult(
            **{**_valid_provider_kwargs(), "missing_information": [blank_value]}
        )


def test_nonblank_strings_are_stripped_without_altering_content():
    result = ProviderInvestigationResult(
        **{
            **_valid_provider_kwargs(),
            "summary": "  A valid summary.  ",
            "risk_factors": ["  a risk factor  "],
            "recommended_actions": [
                RecommendedAction(
                    priority=1, action="  Do something.  ", reason="  Because evidence.  "
                )
            ],
        }
    )
    assert result.summary == "A valid summary."
    assert result.risk_factors == ["a risk factor"]
    assert result.recommended_actions[0].action == "Do something."
    assert result.recommended_actions[0].reason == "Because evidence."


# --- Correction 3: missing-information semantics ----------------------------


def test_missing_merchant_is_included_in_missing_information():
    context = copy.deepcopy(SAMPLE_CONTEXT)
    context["transaction"]["merchant_name"] = None
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(context)
    assert any("Merchant name" in item for item in result.missing_information)


def test_nonpositive_amount_is_not_described_as_missing_information():
    context = copy.deepcopy(SAMPLE_CONTEXT)
    context["data_quality_issues"] = [
        {
            "rule": "nonpositive_amount",
            "explanation": "The transaction amount is not greater than zero and requires review.",
            "points": 25,
            "evidence": {"amount": 0.0, "expected": "greater_than_zero"},
        }
    ]
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(context)
    assert not any("nonpositive_amount" in item for item in result.missing_information)


def test_customer_reference_mismatch_is_not_described_as_missing_information():
    context = copy.deepcopy(SAMPLE_CONTEXT)
    context["data_quality_issues"] = [
        {
            "rule": "customer_reference_mismatch",
            "explanation": "The recorded customer reference does not match the customer on file.",
            "points": 25,
            "evidence": {
                "recorded_customer_reference": "CUST-9999",
                "expected_customer_reference": "CUST-1001",
            },
        }
    ]
    provider = DeterministicMockCopilotProvider()
    result = provider.generate(context)
    assert not any(
        "customer_reference_mismatch" in item for item in result.missing_information
    )
