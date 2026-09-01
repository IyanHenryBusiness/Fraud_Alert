"""Repository for investigation data access (Phase 5)."""
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import Investigation, RiskAlert, Transaction


class InvestigationRepository:
    """Data access layer for investigations and their constrained context inputs."""

    def __init__(self, db: Session):
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy Session for database operations.
        """
        self.db = db

    def get_alert_with_relations(self, alert_id: int) -> Optional[RiskAlert]:
        """Retrieve a single risk alert with its transaction and customer eagerly loaded.

        Args:
            alert_id: The alert ID.

        Returns:
            RiskAlert object (with .transaction and .customer populated) or
            None if not found.
        """
        return (
            self.db.query(RiskAlert)
            .options(joinedload(RiskAlert.transaction), joinedload(RiskAlert.customer))
            .filter(RiskAlert.alert_id == alert_id)
            .first()
        )

    def get_customer_transaction_count(self, customer_id: int) -> int:
        """Return the total number of transactions for a customer."""
        return (
            self.db.query(func.count(Transaction.transaction_id))
            .filter(Transaction.customer_id == customer_id)
            .scalar()
            or 0
        )

    def get_customer_alert_count(self, customer_id: int) -> int:
        """Return the total number of risk alerts for a customer."""
        return (
            self.db.query(func.count(RiskAlert.alert_id))
            .filter(RiskAlert.customer_id == customer_id)
            .scalar()
            or 0
        )

    def get_customer_max_risk_score(self, customer_id: int) -> int:
        """Return the maximum risk_score among a customer's alerts."""
        return (
            self.db.query(func.max(RiskAlert.risk_score))
            .filter(RiskAlert.customer_id == customer_id)
            .scalar()
            or 0
        )

    def add(self, investigation: Investigation) -> Investigation:
        """Stage a new investigation for insertion. Does not commit.

        Args:
            investigation: A new Investigation instance to persist.

        Returns:
            The staged Investigation instance.
        """
        self.db.add(investigation)
        return investigation
