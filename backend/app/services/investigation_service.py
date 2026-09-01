"""Deterministic mock investigation generation service (Phase 5).

Retrieves a constrained context for a single risk alert, sends it to the
configured provider, validates the result, and persists both the context and
the result as a new Investigation row. Uses dbo.investigation_id_seq through
the ORM -- IDs are never calculated manually.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings as default_settings
from app.models import Investigation
from app.repositories.investigation_repository import InvestigationRepository
from app.schemas.investigation import InvestigationResponse
from app.services.copilot_service import AIProviderError, CopilotProvider, get_copilot_provider
from app.services.investigation_context_service import (
    CustomerAggregates,
    InvestigationContextError,
    build_investigation_context,
)

INVESTIGATION_STATUS_NEW = "NEW"


class AlertNotFoundError(Exception):
    """Raised when the requested alert does not exist."""


class InvestigationGenerationError(Exception):
    """Raised when context building, provider generation, or persistence fails."""


def _naive_utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for DB storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InvestigationService:
    """Orchestrates constrained-context building, mock generation, and persistence."""

    def __init__(self, db: Session, provider: Optional[CopilotProvider] = None):
        self.db = db
        self.repo = InvestigationRepository(db)
        self.provider = provider or get_copilot_provider(default_settings)

    def generate(self, alert_id: int) -> InvestigationResponse:
        """Generate and persist a new investigation for the given alert.

        Args:
            alert_id: The risk alert to investigate.

        Returns:
            The API response schema for the newly created investigation.

        Raises:
            AlertNotFoundError: If no alert with alert_id exists.
            InvestigationGenerationError: If context building, provider
                generation, validation, or persistence fails. The
                transaction is rolled back before this is raised.
        """
        alert = self.repo.get_alert_with_relations(alert_id)
        if alert is None:
            raise AlertNotFoundError(f"Alert {alert_id} not found")

        try:
            aggregates = CustomerAggregates(
                transaction_count=self.repo.get_customer_transaction_count(alert.customer_id),
                alert_count=self.repo.get_customer_alert_count(alert.customer_id),
                max_risk_score=self.repo.get_customer_max_risk_score(alert.customer_id),
            )
            context = build_investigation_context(
                alert=alert,
                transaction=alert.transaction,
                customer=alert.customer,
                aggregates=aggregates,
            )

            result = self.provider.generate(context)

            now = _naive_utc_now()
            investigation = Investigation(
                alert_id=alert.alert_id,
                customer_id=alert.customer_id,
                investigation_status=INVESTIGATION_STATUS_NEW,
                priority=alert.severity,
                assigned_to=None,
                summary=result.summary,
                provider=result.provider,
                context_snapshot=json.dumps(context),
                response_payload=result.model_dump_json(),
                created_at=now,
                updated_at=now,
            )
            self.repo.add(investigation)
            self.db.commit()
            self.db.refresh(investigation)
        except AIProviderError:
            self.db.rollback()
            raise
        except InvestigationContextError as exc:
            self.db.rollback()
            raise InvestigationGenerationError(str(exc)) from exc
        except ValidationError as exc:
            self.db.rollback()
            raise InvestigationGenerationError(
                "Provider result failed validation."
            ) from exc
        except Exception as exc:
            self.db.rollback()
            raise InvestigationGenerationError(
                "Investigation generation failed."
            ) from exc

        return InvestigationResponse(
            investigation_id=investigation.investigation_id,
            alert_id=investigation.alert_id,
            provider=investigation.provider,
            summary=investigation.summary,
            risk_factors=result.risk_factors,
            missing_information=result.missing_information,
            recommended_actions=result.recommended_actions,
            disclaimer=result.disclaimer,
            created_at=investigation.created_at,
        )
