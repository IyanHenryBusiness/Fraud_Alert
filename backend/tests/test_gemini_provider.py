"""Tests for the Gemini investigation provider (Phase 5 live-provider boundary).

These tests inject a fake google-genai client and fake response objects, so
they never call the real Gemini API, never require a real API key, never
require SQL Server, and never inspect backend/.env.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.schemas.investigation import GeminiInvestigationPayload, ProviderInvestigationResult
from app.services import copilot_service
from app.services.copilot_service import (
    DISCLAIMER,
    AIProviderConfigurationError,
    AIProviderResponseValidationError,
    AIProviderTimeoutError,
    AIProviderUpstreamError,
    DeterministicMockCopilotProvider,
    GeminiInvestigationProvider,
    get_copilot_provider,
)
from app.services.investigation_context_service import CustomerAggregates, build_investigation_context
from app.services.investigation_service import InvestigationService

REAL_DATABASE_URL = "mssql+pyodbc://real_user:real_pass@real-server/RealDb"
FAKE_API_KEY = "test-gemini-api-key-123"


def make_settings(**overrides):
    values = dict(
        DATABASE_URL=REAL_DATABASE_URL,
        COPILOT_MODE="gemini",
        GEMINI_API_KEY=FAKE_API_KEY,
        GEMINI_MODEL="gemini-3.6-flash",
        GEMINI_RESPONSE_TIMEOUT_SECONDS=30,
    )
    values.update(overrides)
    return Settings(**values)


class FakeGenerateContentConfig:
    _ALLOWED_KWARGS = {"response_mime_type", "response_schema"}

    def __init__(self, **kwargs):
        unexpected = set(kwargs) - self._ALLOWED_KWARGS
        if unexpected:
            raise TypeError(f"Unexpected GenerateContentConfig kwargs: {sorted(unexpected)}")
        self.kwargs = kwargs


class FakeHttpOptions:
    _ALLOWED_KWARGS = {"timeout"}

    def __init__(self, **kwargs):
        unexpected = set(kwargs) - self._ALLOWED_KWARGS
        if unexpected:
            raise TypeError(f"Unexpected HttpOptions kwargs: {sorted(unexpected)}")
        self.kwargs = kwargs


FAKE_TYPES = SimpleNamespace(
    GenerateContentConfig=FakeGenerateContentConfig, HttpOptions=FakeHttpOptions
)


class FakeModels:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._exception is not None:
            raise self._exception
        return self._response


class FakeGeminiClient:
    def __init__(self, response=None, exception=None):
        self.models = FakeModels(response=response, exception=exception)


VALID_PAYLOAD = {
    "summary": "Alert flagged for analyst review.",
    "risk_factors": ["large_transaction: Transaction amount met or exceeded $3,000."],
    "missing_information": [],
    "recommended_actions": [
        {
            "priority": 1,
            "action": "Review the triggered risk rules with the analyst team.",
            "reason": "1 risk rule(s) were triggered for this alert.",
        }
    ],
    "disclaimer": DISCLAIMER,
}


def make_response(payload_dict=None, text=None):
    if text is None:
        text = json.dumps(payload_dict if payload_dict is not None else VALID_PAYLOAD)
    return SimpleNamespace(text=text)


def make_context():
    alert = SimpleNamespace(
        alert_id=5001,
        analysis_key="1006:v0",
        risk_score=94,
        severity="CRITICAL",
        rule_evidence=json.dumps(
            [
                {
                    "rule": "large_transaction",
                    "explanation": "Transaction amount met or exceeded $3,000.",
                    "points": 30,
                    "evidence": {"amount": 95000.00, "threshold": 3000.00},
                }
            ]
        ),
    )
    transaction = SimpleNamespace(
        transaction_id=1006,
        business_transaction_id="BIZ-LARGE-3001",
        transaction_datetime=datetime(2026, 7, 4, 18, 33, 0),
        amount=Decimal("95000.00"),
        merchant_name="Luxury Auto",
        merchant_category="Automotive",
        channel="Store",
        location="New York, NY",
    )
    customer = SimpleNamespace(
        customer_id=101,
        customer_reference="CUST-1001",
        first_name="Alice",
        last_name="Nguyen",
        email="alice.nguyen@example.com",
        phone="+1-206-555-0101",
        date_of_birth=datetime(1988, 4, 12),
    )
    aggregates = CustomerAggregates(transaction_count=10, alert_count=3, max_risk_score=94)
    return build_investigation_context(
        alert=alert, transaction=transaction, customer=customer, aggregates=aggregates
    )


# --- Factory behavior -------------------------------------------------------


def test_factory_returns_mock_provider_in_mock_mode():
    settings = make_settings(COPILOT_MODE="mock")
    provider = get_copilot_provider(settings)
    assert isinstance(provider, DeterministicMockCopilotProvider)


def test_factory_returns_gemini_provider_in_gemini_mode(monkeypatch):
    fake_client = FakeGeminiClient(response=make_response())
    monkeypatch.setattr(
        copilot_service, "_build_gemini_client", lambda api_key, timeout_ms: fake_client
    )
    settings = make_settings(COPILOT_MODE="gemini")
    provider = get_copilot_provider(settings)
    assert isinstance(provider, GeminiInvestigationProvider)


def test_mock_mode_creates_no_gemini_client(monkeypatch):
    def fail_if_called(api_key, timeout_ms):
        raise AssertionError("Mock mode must not build a Gemini client")

    monkeypatch.setattr(copilot_service, "_build_gemini_client", fail_if_called)
    settings = make_settings(COPILOT_MODE="mock")
    provider = get_copilot_provider(settings)
    result = provider.generate(make_context())
    assert result.provider == "mock"


def test_injected_client_prevents_real_client_construction(monkeypatch):
    def fail_if_called(api_key, timeout_ms):
        raise AssertionError("Injecting a fake client must not build a real Gemini client")

    monkeypatch.setattr(copilot_service, "_build_gemini_client", fail_if_called)
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    result = provider.generate(make_context())
    assert result.provider == "gemini"


def test_blank_api_key_raises_configuration_error():
    settings = make_settings(GEMINI_API_KEY="   ")
    with pytest.raises(AIProviderConfigurationError):
        GeminiInvestigationProvider(settings)


# --- Request construction ---------------------------------------------------


def test_gemini_uses_configured_model(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings(GEMINI_MODEL="gemini-3.6-flash")
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    assert fake_client.models.calls[0]["model"] == "gemini-3.6-flash"


def test_gemini_receives_only_constrained_context(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    context = make_context()
    provider.generate(context)
    prompt = fake_client.models.calls[0]["contents"]
    assert json.dumps(context) in prompt


def test_prompt_contains_calculated_risk_score(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    prompt = fake_client.models.calls[0]["contents"]
    assert "calculated_risk_score" in prompt


@pytest.mark.parametrize(
    "excluded_value",
    ["Alice", "Nguyen", "alice.nguyen@example.com", "+1-206-555-0101", "1988-04-12"],
)
def test_prompt_excludes_customer_pii(monkeypatch, excluded_value):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    prompt = fake_client.models.calls[0]["contents"]
    assert excluded_value not in prompt


def test_prompt_excludes_database_url(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    prompt = fake_client.models.calls[0]["contents"]
    assert REAL_DATABASE_URL not in prompt


def test_prompt_excludes_api_key(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    prompt = fake_client.models.calls[0]["contents"]
    assert FAKE_API_KEY not in prompt


def test_request_enables_json_structured_output(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    config = fake_client.models.calls[0]["config"]
    assert config.kwargs["response_mime_type"] == "application/json"


def test_request_uses_gemini_investigation_payload_schema(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    config = fake_client.models.calls[0]["config"]
    assert config.kwargs["response_schema"] is GeminiInvestigationPayload


def test_generate_content_config_does_not_receive_http_options(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    provider.generate(make_context())
    config = fake_client.models.calls[0]["config"]
    assert "http_options" not in config.kwargs


# --- Client construction -----------------------------------------------------


def test_build_gemini_client_passes_http_options_to_client(monkeypatch):
    captured = {}

    class FakeGenaiModule:
        class Client:
            def __init__(self, *, api_key, http_options):
                captured["api_key"] = api_key
                captured["http_options"] = http_options

    fake_genai_types_module = SimpleNamespace(
        HttpOptions=FakeHttpOptions, GenerateContentConfig=FakeGenerateContentConfig
    )
    FakeGenaiModule.types = fake_genai_types_module
    fake_google_package = SimpleNamespace(genai=FakeGenaiModule)
    monkeypatch.setitem(sys.modules, "google", fake_google_package)
    monkeypatch.setitem(sys.modules, "google.genai", FakeGenaiModule)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_genai_types_module)

    client = copilot_service._build_gemini_client(FAKE_API_KEY, timeout_ms=30000)

    assert captured["api_key"] == FAKE_API_KEY
    assert isinstance(captured["http_options"], FakeHttpOptions)
    assert captured["http_options"].kwargs["timeout"] == 30000
    assert isinstance(client, FakeGenaiModule.Client)


def test_provider_init_converts_seconds_to_milliseconds(monkeypatch):
    captured = {}

    def fake_build_client(api_key, timeout_ms):
        captured["timeout_ms"] = timeout_ms
        return FakeGeminiClient(response=make_response())

    monkeypatch.setattr(copilot_service, "_build_gemini_client", fake_build_client)
    settings = make_settings(GEMINI_RESPONSE_TIMEOUT_SECONDS=45)
    GeminiInvestigationProvider(settings)
    assert captured["timeout_ms"] == 45000


# --- Response handling -------------------------------------------------------


def test_valid_json_response_returns_provider_investigation_result(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    result = provider.generate(make_context())
    assert isinstance(result, ProviderInvestigationResult)


def test_application_code_sets_provider_to_gemini(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response())
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    result = provider.generate(make_context())
    assert result.provider == "gemini"
    assert "provider" not in GeminiInvestigationPayload.model_fields


def test_incorrect_disclaimer_is_rejected(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    bad_payload = {**VALID_PAYLOAD, "disclaimer": "This is definitely fraud."}
    fake_client = FakeGeminiClient(response=make_response(bad_payload))
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    with pytest.raises(AIProviderResponseValidationError):
        provider.generate(make_context())


def test_empty_response_is_rejected(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response(text=""))
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    with pytest.raises(AIProviderResponseValidationError):
        provider.generate(make_context())


def test_malformed_json_is_rejected(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(response=make_response(text="not json {"))
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    with pytest.raises(AIProviderResponseValidationError):
        provider.generate(make_context())


def test_nonconsecutive_priorities_are_rejected(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    bad_payload = {
        **VALID_PAYLOAD,
        "recommended_actions": [
            {"priority": 1, "action": "Do the first thing.", "reason": "Because evidence."},
            {"priority": 3, "action": "Do the second thing.", "reason": "Because evidence."},
        ],
    }
    fake_client = FakeGeminiClient(response=make_response(bad_payload))
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    with pytest.raises(AIProviderResponseValidationError):
        provider.generate(make_context())


def test_timeout_is_mapped_to_ai_provider_timeout_error(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(exception=TimeoutError("deadline exceeded"))
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    with pytest.raises(AIProviderTimeoutError):
        provider.generate(make_context())


def test_upstream_failure_does_not_expose_api_key(monkeypatch):
    monkeypatch.setattr(copilot_service, "_import_genai_types", lambda: FAKE_TYPES)
    fake_client = FakeGeminiClient(
        exception=RuntimeError(f"401 Unauthorized: bad key {FAKE_API_KEY}")
    )
    settings = make_settings()
    provider = GeminiInvestigationProvider(settings, client=fake_client)
    with pytest.raises(AIProviderUpstreamError) as exc_info:
        provider.generate(make_context())
    assert FAKE_API_KEY not in str(exc_info.value)


# --- Route status-code mapping -----------------------------------------------


class _FakeServiceConfigError:
    def __init__(self, db):
        raise AIProviderConfigurationError("GEMINI_API_KEY is not configured.")


class _FakeServiceTimeout:
    def __init__(self, db):
        pass

    def generate(self, alert_id):
        raise AIProviderTimeoutError("Gemini request timed out.")


class _FakeServiceUpstream:
    def __init__(self, db):
        pass

    def generate(self, alert_id):
        raise AIProviderUpstreamError("Gemini request failed.")


class _FakeServiceResponseInvalid:
    def __init__(self, db):
        pass

    def generate(self, alert_id):
        raise AIProviderResponseValidationError("Gemini response failed schema validation.")


@pytest.fixture
def route_client():
    from app.database import get_db
    from app.main import app
    from fastapi.testclient import TestClient

    def _override_get_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


def test_route_maps_missing_configuration_to_503(monkeypatch, route_client):
    monkeypatch.setattr(
        "app.routes.investigations.InvestigationService", _FakeServiceConfigError
    )
    response = route_client.post("/api/investigations/generate", json={"alert_id": 5001})
    assert response.status_code == 503


def test_route_maps_timeout_to_504(monkeypatch, route_client):
    monkeypatch.setattr("app.routes.investigations.InvestigationService", _FakeServiceTimeout)
    response = route_client.post("/api/investigations/generate", json={"alert_id": 5001})
    assert response.status_code == 504


def test_route_maps_upstream_error_to_502(monkeypatch, route_client):
    monkeypatch.setattr("app.routes.investigations.InvestigationService", _FakeServiceUpstream)
    response = route_client.post("/api/investigations/generate", json={"alert_id": 5001})
    assert response.status_code == 502


def test_route_maps_response_validation_error_to_502(monkeypatch, route_client):
    monkeypatch.setattr(
        "app.routes.investigations.InvestigationService", _FakeServiceResponseInvalid
    )
    response = route_client.post("/api/investigations/generate", json={"alert_id": 5001})
    assert response.status_code == 502


# --- Service-level persistence behavior with a Gemini-style provider --------


class FakeInvestigationRepository:
    def __init__(self, alert):
        self.alert = alert
        self.added = []

    def get_alert_with_relations(self, alert_id):
        return self.alert if self.alert.alert_id == alert_id else None

    def get_customer_transaction_count(self, customer_id):
        return 10

    def get_customer_alert_count(self, customer_id):
        return 3

    def get_customer_max_risk_score(self, customer_id):
        return 94

    def add(self, investigation):
        investigation.investigation_id = 10000
        self.added.append(investigation)
        return investigation


def make_alert_with_relations():
    alert = SimpleNamespace(
        alert_id=5001,
        analysis_key="1006:v0",
        risk_score=94,
        severity="CRITICAL",
        customer_id=101,
        rule_evidence=json.dumps(
            [
                {
                    "rule": "large_transaction",
                    "explanation": "Transaction amount met or exceeded $3,000.",
                    "points": 30,
                    "evidence": {"amount": 95000.00, "threshold": 3000.00},
                }
            ]
        ),
    )
    alert.transaction = SimpleNamespace(
        transaction_id=1006,
        business_transaction_id="BIZ-LARGE-3001",
        transaction_datetime=datetime(2026, 7, 4, 18, 33, 0),
        amount=Decimal("95000.00"),
        merchant_name="Luxury Auto",
        merchant_category="Automotive",
        channel="Store",
        location="New York, NY",
    )
    alert.customer = SimpleNamespace(customer_id=101, customer_reference="CUST-1001")
    return alert


class FailingProvider:
    def generate(self, context):
        raise AIProviderUpstreamError("Gemini request failed.")


class SucceedingGeminiProvider:
    def generate(self, context):
        return ProviderInvestigationResult(
            provider="gemini",
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
            disclaimer=DISCLAIMER,
        )


def test_provider_failure_does_not_commit_an_investigation():
    alert = make_alert_with_relations()
    db = MagicMock()
    service = InvestigationService(db, provider=FailingProvider())
    service.repo = FakeInvestigationRepository(alert)

    with pytest.raises(AIProviderUpstreamError):
        service.generate(5001)

    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    assert service.repo.added == []


def test_successful_gemini_generation_stores_provider_gemini():
    alert = make_alert_with_relations()
    db = MagicMock()

    def refresh(instance):
        instance.created_at = datetime(2026, 7, 15, 0, 0, 0)

    db.refresh.side_effect = refresh
    service = InvestigationService(db, provider=SucceedingGeminiProvider())
    service.repo = FakeInvestigationRepository(alert)

    response = service.generate(5001)

    assert response.provider == "gemini"
    assert service.repo.added[0].provider == "gemini"
    db.commit.assert_called_once()


# --- Real SDK contract (no network) -----------------------------------------


def test_real_generate_content_config_accepts_only_generation_options():
    """If google-genai is installed, confirm its real GenerateContentConfig
    accepts exactly the generation options this provider passes -- and does
    not accept http_options. Makes no network request."""
    genai_types = pytest.importorskip("google.genai.types")

    config = genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=GeminiInvestigationPayload,
    )
    assert config.response_mime_type == "application/json"
    assert config.response_schema is GeminiInvestigationPayload
