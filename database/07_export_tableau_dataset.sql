USE FraudInvestigationDb;
GO

/*
    Tableau Public reporting dataset.

    One row per risk alert.

    Deliberately excludes:
    - customer names
    - email addresses
    - phone numbers
    - dates of birth
    - rule-evidence JSON
    - investigation context and response JSON
    - credentials and connection information
*/

SELECT
    ra.alert_id,
    ra.transaction_id,
    ra.customer_id,
    c.customer_reference,
    t.business_transaction_id,
    t.transaction_datetime,
    CAST(t.amount AS DECIMAL(12, 2)) AS transaction_amount,
    t.merchant_name,
    t.merchant_category,
    t.channel,
    t.location,
    ra.alert_type,
    ra.risk_score,
    ra.severity,
    ra.alert_status,
    ra.created_at AS alert_created_at,
    ra.updated_at AS alert_updated_at,

    CASE
        WHEN ra.alert_status IN (N'RESOLVED', N'DISMISSED')
            THEN N'CLOSED'
        ELSE N'ACTIVE'
    END AS alert_workflow_group,

    CASE
        WHEN ra.risk_score >= 80 THEN N'80-100'
        WHEN ra.risk_score >= 50 THEN N'50-79'
        WHEN ra.risk_score >= 25 THEN N'25-49'
        ELSE N'0-24'
    END AS risk_score_band,

    CASE
        WHEN ISJSON(ra.rule_evidence) = 1
            THEN (
                SELECT COUNT(*)
                FROM OPENJSON(ra.rule_evidence)
            )
        ELSE 0
    END AS triggered_rule_count,

    latest_investigation.investigation_id AS latest_investigation_id,
    latest_investigation.investigation_status AS latest_investigation_status,
    latest_investigation.priority AS latest_investigation_priority,
    latest_investigation.provider AS latest_investigation_provider,
    latest_investigation.created_at AS latest_investigation_created_at,

    CASE
        WHEN latest_investigation.investigation_id IS NULL THEN 0
        ELSE 1
    END AS has_ai_investigation

FROM dbo.risk_alerts AS ra
INNER JOIN dbo.transactions AS t
    ON t.transaction_id = ra.transaction_id
INNER JOIN dbo.customers AS c
    ON c.customer_id = ra.customer_id

OUTER APPLY (
    SELECT TOP (1)
        i.investigation_id,
        i.investigation_status,
        i.priority,
        i.provider,
        i.created_at
    FROM dbo.investigations AS i
    WHERE i.alert_id = ra.alert_id
    ORDER BY
        i.created_at DESC,
        i.investigation_id DESC
) AS latest_investigation

ORDER BY
    ra.updated_at DESC,
    ra.alert_id DESC;
GO

