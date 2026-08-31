"""Pydantic schemas for the deterministic risk-analysis batch endpoint."""
from pydantic import BaseModel, Field


class SeverityTotals(BaseModel):
    """Count of reportable alerts in the current batch, per severity band."""

    LOW: int = 0
    MEDIUM: int = 0
    HIGH: int = 0
    CRITICAL: int = 0


class AnalysisRunResult(BaseModel):
    """Summary returned after running a batch risk analysis."""

    ruleset_version: str = Field(..., description="Ruleset version applied, e.g. 'v1'")
    transactions_analyzed: int = Field(..., description="Total transactions in the batch")
    alerts_created: int = Field(..., description="New alerts created for this run")
    alerts_updated: int = Field(..., description="Existing v1 alerts updated for this run")
    transactions_without_alerts: int = Field(
        ..., description="Transactions with a final risk_score of zero"
    )
    quality_issues_found: int = Field(
        ..., description="Total data-quality rules found across all transactions"
    )
    severity_totals: SeverityTotals = Field(
        ..., description="Count of reportable alerts per severity band"
    )
