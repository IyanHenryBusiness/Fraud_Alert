"""Tests for alert schemas and evidence parsing."""
import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.routes.alerts import parse_triggered_rules
from app.schemas import AlertDetail, AlertListItem, AlertStatusUpdate, TriggeredRule


class TestTriggeredRule:
    """Tests for TriggeredRule schema."""

    def test_valid_triggered_rule(self):
        """Test creating a valid TriggeredRule."""
        rule_data = {
            "rule": "large_transaction",
            "explanation": "Transaction amount exceeded threshold.",
            "points": 30,
            "evidence": {"amount": 5000.0, "threshold": 3000.0},
        }
        rule = TriggeredRule(**rule_data)
        assert rule.rule == "large_transaction"
        assert rule.points == 30
        assert rule.evidence["amount"] == 5000.0

    def test_triggered_rule_missing_field(self):
        """Test that TriggeredRule rejects missing required fields."""
        with pytest.raises(ValidationError):
            TriggeredRule(
                rule="test",
                explanation="test",
                # Missing 'points' and 'evidence'
            )


class TestAlertListItem:
    """Tests for AlertListItem schema."""

    def test_valid_alert_list_item(self):
        """Test creating a valid AlertListItem."""
        now = datetime.utcnow()
        item = AlertListItem(
            alert_id=1,
            transaction_id=100,
            customer_id=10,
            analysis_key="test_key",
            alert_type="LARGE_TRANSACTION",
            risk_score=85,
            severity="HIGH",
            alert_status="OPEN",
            created_at=now,
            updated_at=now,
        )
        assert item.alert_id == 1
        assert item.severity == "HIGH"
        assert item.alert_status == "OPEN"

    def test_alert_list_item_invalid_severity(self):
        """Test that AlertListItem rejects invalid severity."""
        now = datetime.utcnow()
        with pytest.raises(ValidationError):
            AlertListItem(
                alert_id=1,
                transaction_id=100,
                customer_id=10,
                analysis_key="test_key",
                alert_type="TEST",
                risk_score=50,
                severity="INVALID",  # Invalid severity
                alert_status="OPEN",
                created_at=now,
                updated_at=now,
            )

    def test_alert_list_item_invalid_status(self):
        """Test that AlertListItem rejects invalid status."""
        now = datetime.utcnow()
        with pytest.raises(ValidationError):
            AlertListItem(
                alert_id=1,
                transaction_id=100,
                customer_id=10,
                analysis_key="test_key",
                alert_type="TEST",
                risk_score=50,
                severity="HIGH",
                alert_status="INVALID",  # Invalid status
                created_at=now,
                updated_at=now,
            )


class TestAlertStatusUpdate:
    """Tests for AlertStatusUpdate schema."""

    def test_valid_status_update_with_notes(self):
        """Test creating a valid AlertStatusUpdate with notes."""
        update = AlertStatusUpdate(
            alert_status="ACKNOWLEDGED",
            notes="Analyst reviewed this alert.",
        )
        assert update.alert_status == "ACKNOWLEDGED"
        assert update.notes == "Analyst reviewed this alert."

    def test_valid_status_update_without_notes(self):
        """Test that notes can be omitted in AlertStatusUpdate."""
        update = AlertStatusUpdate(
            alert_status="RESOLVED",
        )
        assert update.alert_status == "RESOLVED"
        assert update.notes is None

    def test_status_update_notes_max_length(self):
        """Test that notes field respects max_length constraint."""
        # Notes can be up to 500 characters
        long_notes = "x" * 500
        update = AlertStatusUpdate(
            alert_status="ACKNOWLEDGED",
            notes=long_notes,
        )
        assert update.notes == long_notes

    def test_status_update_notes_too_long(self):
        """Test that AlertStatusUpdate rejects notes exceeding max_length."""
        too_long_notes = "x" * 501
        with pytest.raises(ValidationError):
            AlertStatusUpdate(
                alert_status="ACKNOWLEDGED",
                notes=too_long_notes,
            )

    def test_status_update_invalid_status(self):
        """Test that AlertStatusUpdate rejects invalid status."""
        with pytest.raises(ValidationError):
            AlertStatusUpdate(
                alert_status="INVALID",
            )

    @pytest.mark.parametrize(
        "valid_status",
        ["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"],
    )
    def test_status_update_all_valid_statuses(self, valid_status):
        """Test that AlertStatusUpdate accepts all valid statuses."""
        update = AlertStatusUpdate(alert_status=valid_status)
        assert update.alert_status == valid_status


class TestAlertDetail:
    """Tests for AlertDetail schema."""

    def test_valid_alert_detail(self):
        """Test creating a valid AlertDetail with triggered_rules."""
        now = datetime.utcnow()
        rules = [
            TriggeredRule(
                rule="test_rule",
                explanation="Test explanation",
                points=20,
                evidence={"key": "value"},
            )
        ]
        detail = AlertDetail(
            alert_id=1,
            transaction_id=100,
            customer_id=10,
            analysis_key="test_key",
            alert_type="TEST",
            risk_score=70,
            severity="MEDIUM",
            alert_status="OPEN",
            triggered_rules=rules,
            notes="Test note",
            created_at=now,
            updated_at=now,
        )
        assert detail.alert_id == 1
        assert len(detail.triggered_rules) == 1
        assert detail.triggered_rules[0].rule == "test_rule"

    def test_alert_detail_triggered_rules_required(self):
        """Test that AlertDetail requires triggered_rules."""
        now = datetime.utcnow()
        with pytest.raises(ValidationError):
            AlertDetail(
                alert_id=1,
                transaction_id=100,
                customer_id=10,
                analysis_key="test_key",
                alert_type="TEST",
                risk_score=70,
                severity="MEDIUM",
                alert_status="OPEN",
                # Missing triggered_rules
                created_at=now,
                updated_at=now,
            )


class TestEvidenceParsing:
    """Tests for rule_evidence JSON parsing."""

    def test_parse_valid_json_array(self):
        """Test parsing valid rule_evidence JSON array."""
        evidence_json = json.dumps(
            [
                {
                    "rule": "large_transaction",
                    "explanation": "Amount exceeded threshold.",
                    "points": 30,
                    "evidence": {"amount": 5000.0, "threshold": 3000.0},
                }
            ]
        )
        rules = parse_triggered_rules(evidence_json)
        assert len(rules) == 1
        assert rules[0].rule == "large_transaction"
        assert rules[0].points == 30

    def test_parse_multiple_rules(self):
        """Test parsing multiple rules from JSON."""
        evidence_json = json.dumps(
            [
                {
                    "rule": "rule_1",
                    "explanation": "First rule",
                    "points": 20,
                    "evidence": {},
                },
                {
                    "rule": "rule_2",
                    "explanation": "Second rule",
                    "points": 30,
                    "evidence": {},
                },
            ]
        )
        rules = parse_triggered_rules(evidence_json)
        assert len(rules) == 2

    def test_parse_empty_json_array(self):
        """Test parsing empty JSON array."""
        evidence_json = json.dumps([])
        rules = parse_triggered_rules(evidence_json)
        assert rules == []

    def test_parse_malformed_json(self):
        """Test that malformed JSON returns empty list."""
        malformed_json = "{invalid json"
        rules = parse_triggered_rules(malformed_json)
        assert rules == []

    def test_parse_json_non_array(self):
        """Test that non-array JSON returns empty list."""
        non_array_json = json.dumps({"rule": "test"})
        rules = parse_triggered_rules(non_array_json)
        assert rules == []

    def test_parse_json_with_invalid_item(self):
        """Test that items with missing fields are skipped."""
        evidence_json = json.dumps(
            [
                {
                    "rule": "valid_rule",
                    "explanation": "Valid",
                    "points": 20,
                    "evidence": {},
                },
                {
                    "rule": "invalid_rule",
                    # Missing required fields
                },
            ]
        )
        rules = parse_triggered_rules(evidence_json)
        # Should skip the invalid item and return only the valid one
        assert len(rules) == 1
        assert rules[0].rule == "valid_rule"

    def test_parse_empty_string(self):
        """Test that empty string returns empty list."""
        rules = parse_triggered_rules("")
        assert rules == []
