"""Pydantic models for risk alert API schemas."""
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class TriggeredRule(BaseModel):
    """A triggered risk-analysis rule with supporting evidence."""

    rule: str = Field(
        ..., description="The rule identifier (e.g., 'large_transaction')"
    )
    explanation: str = Field(
        ...,
        description="Human-readable explanation of why the rule triggered",
    )
    points: int = Field(
        ..., description="Risk points awarded by this rule"
    )
    evidence: dict[str, Any] = Field(
        ..., description="Evidence data supporting the rule"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "rule": "large_transaction",
                "explanation": "Transaction amount met or exceeded $3,000.",
                "points": 30,
                "evidence": {"amount": 4250.0, "threshold": 3000.0},
            }
        }
    }


class AlertListItem(BaseModel):
    """Minimal alert information for list views."""

    alert_id: int
    transaction_id: int
    customer_id: int
    analysis_key: str
    alert_type: str
    risk_score: int
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    alert_status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertDetail(BaseModel):
    """Complete alert information with parsed risk-analysis rules."""

    alert_id: int
    transaction_id: int
    customer_id: int
    analysis_key: str
    alert_type: str
    risk_score: int
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    alert_status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"]
    triggered_rules: List[TriggeredRule] = Field(
        ..., description="Parsed rules from rule_evidence JSON"
    )
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertStatusUpdate(BaseModel):
    """Request to update an alert's status."""

    alert_status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"] = Field(
        ..., description="New status for the alert"
    )
    notes: Optional[str] = Field(
        None, max_length=500, description="Optional notes about the status change"
    )

    model_config = {"json_schema_extra": {
        "example": {
            "alert_status": "ACKNOWLEDGED",
            "notes": "Analyst reviewed transaction, appears legitimate."
        }
    }}
