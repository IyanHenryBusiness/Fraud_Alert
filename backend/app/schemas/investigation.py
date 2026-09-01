"""Pydantic schemas for the Phase 5 mock/Gemini investigation generation API."""
from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DISCLAIMER = (
    "This result supports analyst review and does not establish that fraud occurred."
)


def _require_nonblank(value: str) -> str:
    """Strip whitespace and reject empty or whitespace-only strings."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be empty or whitespace-only")
    return stripped


def _require_consecutive_priorities_from_one(actions: "List[RecommendedAction]") -> None:
    """Ensure recommended_actions priorities start at 1 and are consecutive."""
    priorities = [action.priority for action in actions]
    if priorities != list(range(1, len(priorities) + 1)):
        raise ValueError(
            "recommended_actions priorities must start at 1 and be consecutive"
        )


class InvestigationGenerateRequest(BaseModel):
    """Request to generate an investigation for a single risk alert."""

    alert_id: int = Field(..., gt=0, description="The risk alert to investigate")


class RecommendedAction(BaseModel):
    """A single evidence-based action recommended to the analyst."""

    priority: int = Field(..., ge=1, description="1-based, consecutive priority order")
    action: str = Field(..., min_length=1, description="The recommended action to take")
    reason: str = Field(..., min_length=1, description="Evidence-based reason for the action")

    @field_validator("action", "reason")
    @classmethod
    def _validate_nonblank(cls, value: str) -> str:
        return _require_nonblank(value)


class ProviderInvestigationResult(BaseModel):
    """Validated output produced by any investigation provider."""

    provider: Literal["mock", "copilot_studio", "gemini"]
    summary: str = Field(..., min_length=1)
    risk_factors: List[str] = Field(..., description="Risk factors derived from triggered rules")
    missing_information: List[str] = Field(
        ..., description="Information gaps identified honestly from the context"
    )
    recommended_actions: List[RecommendedAction] = Field(
        ..., description="Evidence-based actions, numbered consecutively starting at 1"
    )
    disclaimer: str = Field(..., min_length=1)

    @field_validator("summary", "disclaimer")
    @classmethod
    def _validate_nonblank(cls, value: str) -> str:
        return _require_nonblank(value)

    @field_validator("risk_factors", "missing_information")
    @classmethod
    def _validate_items_nonblank(cls, value: List[str]) -> List[str]:
        return [_require_nonblank(item) for item in value]


class GeminiInvestigationPayload(BaseModel):
    """Model-generated investigation content validated before use.

    Does not include ``provider`` -- the application, not Gemini, sets
    ``provider="gemini"`` after this payload passes validation.
    """

    summary: str = Field(..., min_length=1)
    risk_factors: List[str] = Field(..., description="Risk factors derived from triggered rules")
    missing_information: List[str] = Field(
        ..., description="Information gaps identified honestly from the context"
    )
    recommended_actions: List[RecommendedAction] = Field(
        ..., description="Evidence-based actions, numbered consecutively starting at 1"
    )
    disclaimer: str = Field(..., min_length=1)

    @field_validator("summary", "disclaimer")
    @classmethod
    def _validate_nonblank(cls, value: str) -> str:
        return _require_nonblank(value)

    @field_validator("risk_factors", "missing_information")
    @classmethod
    def _validate_items_nonblank(cls, value: List[str]) -> List[str]:
        return [_require_nonblank(item) for item in value]

    @model_validator(mode="after")
    def _validate_disclaimer_and_priorities(self) -> "GeminiInvestigationPayload":
        if self.disclaimer != DISCLAIMER:
            raise ValueError("disclaimer must exactly match the required disclaimer text")
        _require_consecutive_priorities_from_one(self.recommended_actions)
        return self


class InvestigationResponse(BaseModel):
    """API response for a newly generated investigation."""

    investigation_id: int
    alert_id: int
    provider: Literal["mock", "copilot_studio", "gemini"]
    summary: str
    risk_factors: List[str]
    missing_information: List[str]
    recommended_actions: List[RecommendedAction]
    disclaimer: str
    created_at: datetime

    model_config = {"from_attributes": True}

