"""Investigation content providers (Phase 5).

Defines the provider interface used by InvestigationService, the
deterministic offline mock implementation, and a real Google Gemini
implementation used when COPILOT_MODE="gemini". Copilot Studio / Direct Line
are not implemented and are not called.
"""
from __future__ import annotations

import json
from typing import Any, Optional, Protocol

from pydantic import ValidationError

from app.config import Settings
from app.schemas.investigation import (
    DISCLAIMER,
    GeminiInvestigationPayload,
    ProviderInvestigationResult,
    RecommendedAction,
)


class AIProviderError(Exception):
    """Base class for controlled, non-leaking AI-provider errors."""


class AIProviderConfigurationError(AIProviderError):
    """Raised when the configured provider is missing required configuration."""


class AIProviderTimeoutError(AIProviderError):
    """Raised when a provider request exceeds the configured timeout."""


class AIProviderUpstreamError(AIProviderError):
    """Raised when the upstream API returns an auth, quota, network, or other failure."""


class AIProviderResponseValidationError(AIProviderError):
    """Raised when a response is empty, malformed, or fails schema/business validation."""


class CopilotProvider(Protocol):
    """Interface every investigation content provider must implement."""

    def generate(self, context: dict[str, Any]) -> ProviderInvestigationResult:
        """Generate investigation content from a constrained context dict."""
        ...


class DeterministicMockCopilotProvider:
    """Deterministic, offline mock provider used when COPILOT_MODE="mock".

    Performs no HTTP or network calls, uses only the supplied context, and
    returns identical content for identical context. Never asserts that
    fraud occurred; only surfaces evidence for analyst review.
    """

    def generate(self, context: dict[str, Any]) -> ProviderInvestigationResult:
        """Build a ProviderInvestigationResult entirely from the supplied context."""
        triggered_rules = context.get("triggered_rules", [])
        data_quality_issues = context.get("data_quality_issues", [])
        transaction = context.get("transaction", {})
        customer = context.get("customer", {})

        risk_factors = [
            f"{rule.get('rule')}: {rule.get('explanation')}" for rule in triggered_rules
        ]

        missing_information: list[str] = []
        if not transaction.get("merchant_name"):
            missing_information.append("Merchant name was not recorded for this transaction.")
        if not transaction.get("channel"):
            missing_information.append("Transaction channel was not recorded.")
        if not transaction.get("location"):
            missing_information.append("Transaction location was not recorded.")

        recommended_actions: list[RecommendedAction] = []
        priority = 1
        if triggered_rules:
            recommended_actions.append(
                RecommendedAction(
                    priority=priority,
                    action="Review the triggered risk rules with the analyst team.",
                    reason=f"{len(triggered_rules)} risk rule(s) were triggered for this alert.",
                )
            )
            priority += 1
        if data_quality_issues:
            recommended_actions.append(
                RecommendedAction(
                    priority=priority,
                    action="Confirm transaction data quality with the source system.",
                    reason=f"{len(data_quality_issues)} data-quality issue(s) were detected.",
                )
            )
            priority += 1
        if customer.get("alert_count", 0) > 1:
            recommended_actions.append(
                RecommendedAction(
                    priority=priority,
                    action="Review the customer's alert history for a broader pattern.",
                    reason=f"The customer has {customer.get('alert_count')} alert(s) on file.",
                )
            )
            priority += 1
        if not recommended_actions:
            recommended_actions.append(
                RecommendedAction(
                    priority=priority,
                    action="Confirm alert details with the analyst team.",
                    reason="No specific risk or data-quality rule evidence was available.",
                )
            )

        summary = (
            f"Alert {context.get('alert_id')} ({context.get('severity')} severity, "
            f"risk score {context.get('calculated_risk_score')}) flagged {len(triggered_rules)} "
            f"risk rule(s) and {len(data_quality_issues)} data-quality issue(s) for "
            "analyst review."
        )

        return ProviderInvestigationResult(
            provider="mock",
            summary=summary,
            risk_factors=risk_factors,
            missing_information=missing_information,
            recommended_actions=recommended_actions,
            disclaimer=DISCLAIMER,
        )


def get_copilot_provider(settings: Settings) -> CopilotProvider:
    """Select an investigation provider based on settings.COPILOT_MODE.

    Args:
        settings: Application settings.

    Returns:
        A CopilotProvider implementation for the configured mode.

    Raises:
        AIProviderConfigurationError: If COPILOT_MODE is not a supported
            value, or if the selected provider is missing configuration
            (e.g. a blank GEMINI_API_KEY). Performs no network calls.
    """
    mode = settings.COPILOT_MODE.strip().lower()
    if mode == "mock":
        return DeterministicMockCopilotProvider()
    if mode == "gemini":
        return GeminiInvestigationProvider(settings)
    raise AIProviderConfigurationError(f"Unsupported COPILOT_MODE: {settings.COPILOT_MODE}")


GEMINI_PROMPT_INSTRUCTIONS = [
    "Analyze only the supplied evidence package.",
    "Do not invent facts.",
    "Do not claim fraud occurred.",
    "Treat the result as decision support for a human analyst.",
    "Risk factors must come only from triggered_rules.",
    "Missing information must describe only absent information.",
    "Recommendations must be based only on supplied evidence.",
    "Return the required structured response.",
    f'Use the exact disclaimer: "{DISCLAIMER}"',
]


def _build_gemini_prompt(context: dict[str, Any]) -> str:
    """Build the single prompt sent to Gemini: safety instructions + context JSON.

    Contains only the constrained context (already excludes customer PII,
    credentials, connection strings, environment variables, and unrelated
    transactions) -- no conversation history, memory, or external knowledge.
    """
    instructions = "\n".join(f"- {line}" for line in GEMINI_PROMPT_INSTRUCTIONS)
    return (
        "You are assisting a fraud analyst. Follow these safety instructions:\n"
        f"{instructions}\n\n"
        "Evidence package (JSON):\n"
        f"{json.dumps(context)}"
    )


def _build_gemini_client(api_key: str, timeout_ms: int) -> Any:
    """Construct a real google-genai client with the configured request timeout.

    Raises:
        AIProviderConfigurationError: If the google-genai package is not installed.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AIProviderConfigurationError(
            "The google-genai package is not installed."
        ) from exc
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )


def _import_genai_types() -> Any:
    """Lazily import google.genai.types.

    Raises:
        AIProviderConfigurationError: If the google-genai package is not installed.
    """
    try:
        from google.genai import types
    except ImportError as exc:
        raise AIProviderConfigurationError(
            "The google-genai package is not installed."
        ) from exc
    return types


def _is_timeout_error(exc: Exception) -> bool:
    """Best-effort detection of timeout-style exceptions from any transport."""
    if isinstance(exc, TimeoutError):
        return True
    return "timeout" in type(exc).__name__.lower()


class GeminiInvestigationProvider:
    """Real Google Gemini provider used when COPILOT_MODE="gemini".

    Uses structured JSON output validated against GeminiInvestigationPayload
    before being converted into a ProviderInvestigationResult with
    provider="gemini" set by application code (never by the model).
    """

    def __init__(self, settings: Settings, client: Optional[Any] = None):
        """Initialize the provider.

        Args:
            settings: Application settings (must have a nonblank GEMINI_API_KEY).
            client: Optional pre-built google-genai client, used for tests.
                When supplied, no real client is constructed.

        Raises:
            AIProviderConfigurationError: If GEMINI_API_KEY is blank.
        """
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            raise AIProviderConfigurationError("GEMINI_API_KEY is not configured.")

        self._settings = settings
        if client is not None:
            self._client = client
        else:
            timeout_ms = int(settings.GEMINI_RESPONSE_TIMEOUT_SECONDS * 1000)
            self._client = _build_gemini_client(api_key, timeout_ms)

    def generate(self, context: dict[str, Any]) -> ProviderInvestigationResult:
        """Send the constrained context to Gemini and return a validated result.

        Raises:
            AIProviderTimeoutError: If the request exceeds the configured timeout.
            AIProviderUpstreamError: If the upstream API call otherwise fails.
            AIProviderResponseValidationError: If the response is empty,
                malformed, or fails schema/business-rule validation.
        """
        types = _import_genai_types()
        prompt = _build_gemini_prompt(context)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiInvestigationPayload,
        )

        try:
            response = self._client.models.generate_content(
                model=self._settings.GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            if _is_timeout_error(exc):
                raise AIProviderTimeoutError("Gemini request timed out.") from exc
            raise AIProviderUpstreamError("Gemini request failed.") from exc

        text = getattr(response, "text", None)
        if not text or not text.strip():
            raise AIProviderResponseValidationError("Gemini returned an empty response.")

        try:
            payload = GeminiInvestigationPayload.model_validate_json(text)
        except ValidationError as exc:
            raise AIProviderResponseValidationError(
                "Gemini response failed schema validation."
            ) from exc

        return ProviderInvestigationResult(
            provider="gemini",
            summary=payload.summary,
            risk_factors=payload.risk_factors,
            missing_information=payload.missing_information,
            recommended_actions=payload.recommended_actions,
            disclaimer=payload.disclaimer,
        )

