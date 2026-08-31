"""Repository for transaction data access used by risk analysis."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Transaction


class TransactionRepository:
    """Data access layer for transactions joined with customer data."""

    def __init__(self, db: Session):
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy Session for database operations.
        """
        self.db = db

    def get_transactions_for_analysis(self) -> list[dict[str, Any]]:
        """Return every transaction joined to its customer for risk analysis.

        Does not commit or modify data; this is a read-only query.

        Returns:
            List of dicts with transaction_id, customer_id,
            business_transaction_id, transaction_datetime,
            recorded_customer_reference, customer_reference, amount,
            merchant_name, merchant_category, channel, and location, ordered
            by customer_id, transaction_datetime, transaction_id.
        """
        stmt = (
            select(
                Transaction.transaction_id,
                Transaction.customer_id,
                Transaction.business_transaction_id,
                Transaction.transaction_datetime,
                Transaction.recorded_customer_reference,
                Customer.customer_reference.label("customer_reference"),
                Transaction.amount,
                Transaction.merchant_name,
                Transaction.merchant_category,
                Transaction.channel,
                Transaction.location,
            )
            .join(Customer, Customer.customer_id == Transaction.customer_id)
            .order_by(
                Transaction.customer_id,
                Transaction.transaction_datetime,
                Transaction.transaction_id,
            )
        )
        rows = self.db.execute(stmt).mappings().all()
        return [dict(row) for row in rows]
