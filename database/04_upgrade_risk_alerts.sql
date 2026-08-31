USE FraudInvestigationDb;
GO

SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    ------------------------------------------------------------
    -- 1. Create a sequence for automatically generated alert IDs.
    ------------------------------------------------------------
    IF OBJECT_ID(N'dbo.risk_alert_id_seq', N'SO') IS NULL
    BEGIN
        EXEC(N'
            CREATE SEQUENCE dbo.risk_alert_id_seq
                AS INT
                START WITH 6000
                INCREMENT BY 1;
        ');
    END;

    ------------------------------------------------------------
    -- 2. Add analysis_key as nullable temporarily.
    ------------------------------------------------------------
    IF COL_LENGTH(N'dbo.risk_alerts', N'analysis_key') IS NULL
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD analysis_key NVARCHAR(200) NULL;
    END;

    ------------------------------------------------------------
    -- 3. Give existing alerts stable legacy analysis keys.
    ------------------------------------------------------------
    UPDATE dbo.risk_alerts
    SET analysis_key = CONCAT(
        CAST(transaction_id AS NVARCHAR(50)),
        N':v0:',
        CAST(alert_id AS NVARCHAR(50))
    )
    WHERE analysis_key IS NULL
       OR LTRIM(RTRIM(analysis_key)) = N'';

    ------------------------------------------------------------
    -- 4. Make analysis_key required.
    ------------------------------------------------------------
    ALTER TABLE dbo.risk_alerts
    ALTER COLUMN analysis_key NVARCHAR(200) NOT NULL;

    ------------------------------------------------------------
    -- 5. Add rule_evidence as nullable temporarily.
    ------------------------------------------------------------
    IF COL_LENGTH(N'dbo.risk_alerts', N'rule_evidence') IS NULL
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD rule_evidence NVARCHAR(MAX) NULL;
    END;

    ------------------------------------------------------------
    -- 6. Convert existing alert information into JSON evidence.
    ------------------------------------------------------------
    UPDATE dbo.risk_alerts
    SET rule_evidence = (
        SELECT
            LOWER(alert_type) AS [rule],
            N'Legacy seeded alert migrated to explainable rule evidence.'
                AS [explanation],
            risk_score AS [points],
            JSON_QUERY(
                (
                    SELECT
                        transaction_id AS [transaction_id],
                        notes AS [legacy_notes]
                    FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
                )
            ) AS [evidence]
        FOR JSON PATH
    )
    WHERE rule_evidence IS NULL
       OR ISJSON(rule_evidence) <> 1;

    ------------------------------------------------------------
    -- 7. Make evidence required.
    ------------------------------------------------------------
    ALTER TABLE dbo.risk_alerts
    ALTER COLUMN rule_evidence NVARCHAR(MAX) NOT NULL;

    ------------------------------------------------------------
    -- 8. Add updated_at.
    ------------------------------------------------------------
    IF COL_LENGTH(N'dbo.risk_alerts', N'updated_at') IS NULL
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD updated_at DATETIME2 NULL;
    END;

    UPDATE dbo.risk_alerts
    SET updated_at = COALESCE(updated_at, created_at, SYSUTCDATETIME())
    WHERE updated_at IS NULL;

    ALTER TABLE dbo.risk_alerts
    ALTER COLUMN updated_at DATETIME2 NOT NULL;

    ------------------------------------------------------------
    -- 9. Add alert_id automatic default.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c
            ON c.object_id = dc.parent_object_id
           AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = OBJECT_ID(N'dbo.risk_alerts')
          AND c.name = N'alert_id'
    )
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD CONSTRAINT DF_risk_alerts_alert_id
        DEFAULT (NEXT VALUE FOR dbo.risk_alert_id_seq)
        FOR alert_id;
    END;

    ------------------------------------------------------------
    -- 10. Add defaults for new columns.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.risk_alerts')
          AND name = N'DF_risk_alerts_rule_evidence'
    )
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD CONSTRAINT DF_risk_alerts_rule_evidence
        DEFAULT (N'[]') FOR rule_evidence;
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.risk_alerts')
          AND name = N'DF_risk_alerts_updated_at'
    )
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD CONSTRAINT DF_risk_alerts_updated_at
        DEFAULT SYSUTCDATETIME() FOR updated_at;
    END;

    ------------------------------------------------------------
    -- 11. Add uniqueness protection.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.risk_alerts')
          AND name = N'UX_risk_alerts_analysis_key'
    )
    BEGIN
        CREATE UNIQUE INDEX UX_risk_alerts_analysis_key
            ON dbo.risk_alerts(analysis_key);
    END;

    ------------------------------------------------------------
    -- 12. Require valid JSON.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.risk_alerts')
          AND name = N'CK_risk_alerts_rule_evidence_json'
    )
    BEGIN
        ALTER TABLE dbo.risk_alerts
        ADD CONSTRAINT CK_risk_alerts_rule_evidence_json
        CHECK (ISJSON(rule_evidence) = 1);
    END;

    ------------------------------------------------------------
    -- 13. Add reporting index.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.risk_alerts')
          AND name = N'IX_risk_alerts_severity_status'
    )
    BEGIN
        CREATE INDEX IX_risk_alerts_severity_status
            ON dbo.risk_alerts(
                severity,
                alert_status,
                updated_at
            );
    END;

    ------------------------------------------------------------
    -- 14. Remove the amount constraint so Pandas can detect
    --     deliberately negative data-quality examples.
    ------------------------------------------------------------
    IF EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.transactions')
          AND name = N'CK_transactions_amount'
    )
    BEGIN
        ALTER TABLE dbo.transactions
        DROP CONSTRAINT CK_transactions_amount;
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO
