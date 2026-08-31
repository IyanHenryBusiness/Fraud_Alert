"""Deterministic risk-analysis batch service (Phase 4).

Orchestrates the pure data-quality and risk-analysis engines against the
current transaction/customer data and persists the resulting alerts using
an idempotent upsert keyed on analysis_key.
"""
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models import RiskAlert
from app.repositories import AlertRepository, TransactionRepository
from app.schemas.analysis import AnalysisRunResult, SeverityTotals
from app.services.data_quality_service import analyze_data_quality
from app.services.risk_service import analyze_risk

RULESET_VERSION = "v1"
ALERT_TYPE = "RULE_ANALYSIS"
ALERT_STATUS_OPEN = "OPEN"
SEVERITY_KEYS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _naive_utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for DB storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _empty_result() -> AnalysisRunResult:
    return AnalysisRunResult(
        ruleset_version=RULESET_VERSION,
        transactions_analyzed=0,
        alerts_created=0,
        alerts_updated=0,
        transactions_without_alerts=0,
        quality_issues_found=0,
        severity_totals=SeverityTotals(),
    )


class AnalysisService:
    """Runs the data-quality and risk-analysis engines and persists resulting alerts."""

    def __init__(self, db: Session):
        self.db = db
        self.transaction_repo = TransactionRepository(db)
        self.alert_repo = AlertRepository(db)

    def run(self) -> AnalysisRunResult:
        """Execute a full analysis batch and persist reportable alerts.

        Returns:
            Summary counts for the batch.

        Raises:
            Exception: Re-raised after rollback if analysis or persistence fails.
        """
        try:
            records = self.transaction_repo.get_transactions_for_analysis()
            if not records:
                return _empty_result()

            df = pd.DataFrame.from_records(records)
            quality_results = analyze_data_quality(df)
            risk_results = analyze_risk(df, quality_results)

            quality_issues_found = sum(len(rules) for rules in quality_results.values())
            customer_id_by_tid = {
                int(row["transaction_id"]): int(row["customer_id"]) for row in records
            }

            alerts_created = 0
            alerts_updated = 0
            transactions_without_alerts = 0
            severity_totals = {key: 0 for key in SEVERITY_KEYS}
            now = _naive_utc_now()

            for transaction_id in sorted(risk_results):
                result = risk_results[transaction_id]
                risk_score = result["risk_score"]

                if risk_score <= 0:
                    transactions_without_alerts += 1
                    continue

                severity = result["severity"]
                rule_evidence = json.dumps(result["rules"])
                analysis_key = f"{transaction_id}:{RULESET_VERSION}"
                severity_totals[severity] = severity_totals.get(severity, 0) + 1

                existing = self.alert_repo.get_by_analysis_key(analysis_key)
                if existing is not None:
                    self.alert_repo.update_calculated_fields(
                        existing,
                        alert_type=ALERT_TYPE,
                        risk_score=risk_score,
                        severity=severity,
                        rule_evidence=rule_evidence,
                        updated_at=now,
                    )
                    alerts_updated += 1
                else:
                    new_alert = RiskAlert(
                        transaction_id=transaction_id,
                        customer_id=customer_id_by_tid[transaction_id],
                        analysis_key=analysis_key,
                        alert_type=ALERT_TYPE,
                        risk_score=risk_score,
                        severity=severity,
                        alert_status=ALERT_STATUS_OPEN,
                        rule_evidence=rule_evidence,
                        notes=None,
                        created_at=now,
                        updated_at=now,
                    )
                    self.alert_repo.add(new_alert)
                    alerts_created += 1

            self.db.flush()
            self.db.commit()

            return AnalysisRunResult(
                ruleset_version=RULESET_VERSION,
                transactions_analyzed=len(df),
                alerts_created=alerts_created,
                alerts_updated=alerts_updated,
                transactions_without_alerts=transactions_without_alerts,
                quality_issues_found=quality_issues_found,
                severity_totals=SeverityTotals(**severity_totals),
            )
        except Exception:
            self.db.rollback()
            raise
