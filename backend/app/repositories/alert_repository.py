"""Repository for alert data access."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import RiskAlert


class AlertRepository:
    """Data access layer for risk alerts."""

    def __init__(self, db: Session):
        """Initialize repository with database session.
        
        Args:
            db: SQLAlchemy Session for database operations.
        """
        self.db = db

    def list_alerts(
        self,
        severity: Optional[str] = None,
        alert_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[RiskAlert]:
        """List alerts with optional filtering.
        
        Args:
            severity: Filter by severity (LOW, MEDIUM, HIGH, CRITICAL).
            alert_status: Filter by status (OPEN, ACKNOWLEDGED, RESOLVED, DISMISSED).
            limit: Maximum number of results.
            offset: Number of results to skip.
            
        Returns:
            List of RiskAlert objects ordered by risk_score descending, alert_id ascending.
        """
        query = self.db.query(RiskAlert)
        
        if severity:
            query = query.filter(RiskAlert.severity == severity)
        
        if alert_status:
            query = query.filter(RiskAlert.alert_status == alert_status)
        
        query = query.order_by(desc(RiskAlert.risk_score), RiskAlert.alert_id)
        
        return query.offset(offset).limit(limit).all()

    def get_alert_by_id(self, alert_id: int) -> Optional[RiskAlert]:
        """Retrieve a single alert by ID.
        
        Args:
            alert_id: The alert ID.
            
        Returns:
            RiskAlert object or None if not found.
        """
        return self.db.query(RiskAlert).filter(RiskAlert.alert_id == alert_id).first()

    def update_alert_status(
        self,
        alert_id: int,
        new_status: str,
        notes: Optional[str] = None,
    ) -> Optional[RiskAlert]:
        """Update alert status and optional notes.
        
        Preserves all other fields (alert_id, transaction_id, customer_id, 
        analysis_key, alert_type, risk_score, severity, created_at).
        
        Args:
            alert_id: The alert ID to update.
            new_status: The new alert_status (OPEN, ACKNOWLEDGED, RESOLVED, DISMISSED).
            notes: Optional notes about the status change. If None, existing notes are preserved.
            
        Returns:
            Updated RiskAlert object or None if not found.
            
        Raises:
            Exception: If database commit fails (rollback happens automatically).
        """
        alert = self.db.query(RiskAlert).filter(RiskAlert.alert_id == alert_id).first()
        
        if not alert:
            return None
        
        try:
            alert.alert_status = new_status
            if notes is not None:
                alert.notes = notes
            alert.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(alert)
            return alert
        except Exception:
            self.db.rollback()
            raise
