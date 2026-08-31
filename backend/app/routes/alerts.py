"""Routes for risk alert management."""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RiskAlert
from app.repositories import AlertRepository
from app.schemas import AlertDetail, AlertListItem, AlertStatusUpdate, TriggeredRule

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def parse_triggered_rules(rule_evidence: str) -> List[TriggeredRule]:
    """Parse rule_evidence JSON string into TriggeredRule objects.
    
    Args:
        rule_evidence: JSON string containing array of rule evidence.
        
    Returns:
        List of TriggeredRule objects. Returns empty list on parse errors.
    """
    try:
        parsed = json.loads(rule_evidence)
        if not isinstance(parsed, list):
            return []
        rules = []
        for item in parsed:
            try:
                rule = TriggeredRule(**item)
                rules.append(rule)
            except Exception:
                # Skip malformed items rather than fail entire list
                continue
        return rules
    except json.JSONDecodeError:
        # Return empty list for malformed JSON
        return []


def alert_to_detail(alert: RiskAlert) -> AlertDetail:
    """Convert RiskAlert ORM model to AlertDetail schema.
    
    Args:
        alert: RiskAlert ORM object from database.
        
    Returns:
        AlertDetail schema with parsed triggered_rules.
    """
    triggered_rules = parse_triggered_rules(alert.rule_evidence)
    
    return AlertDetail(
        alert_id=alert.alert_id,
        transaction_id=alert.transaction_id,
        customer_id=alert.customer_id,
        analysis_key=alert.analysis_key,
        alert_type=alert.alert_type,
        risk_score=alert.risk_score,
        severity=alert.severity,
        alert_status=alert.alert_status,
        triggered_rules=triggered_rules,
        notes=alert.notes,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("", response_model=List[AlertListItem])
def list_alerts(
    db: Session = Depends(get_db),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    alert_status: Optional[str] = Query(None, description="Filter by alert status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[AlertListItem]:
    """List all alerts with optional filtering.
    
    Severity filter: LOW, MEDIUM, HIGH, CRITICAL
    Status filter: OPEN, ACKNOWLEDGED, RESOLVED, DISMISSED
    """
    repo = AlertRepository(db)
    alerts = repo.list_alerts(
        severity=severity,
        alert_status=alert_status,
        limit=limit,
        offset=offset,
    )
    return [
        AlertListItem(
            alert_id=a.alert_id,
            transaction_id=a.transaction_id,
            customer_id=a.customer_id,
            analysis_key=a.analysis_key,
            alert_type=a.alert_type,
            risk_score=a.risk_score,
            severity=a.severity,
            alert_status=a.alert_status,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in alerts
    ]


@router.get("/{alert_id}", response_model=AlertDetail)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db),
) -> AlertDetail:
    """Retrieve a single alert by ID with parsed risk-analysis rules."""
    repo = AlertRepository(db)
    alert = repo.get_alert_by_id(alert_id)
    
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    
    return alert_to_detail(alert)


@router.patch("/{alert_id}/status", response_model=AlertDetail)
def update_alert_status(
    alert_id: int,
    update: AlertStatusUpdate,
    db: Session = Depends(get_db),
) -> AlertDetail:
    """Update an alert's status and optional notes.
    
    Preserves all other fields including alert_id, transaction_id, customer_id,
    analysis_key, alert_type, risk_score, severity, and created_at.
    """
    repo = AlertRepository(db)
    alert = repo.update_alert_status(
        alert_id=alert_id,
        new_status=update.alert_status,
        notes=update.notes,
    )
    
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    
    return alert_to_detail(alert)
