USE FraudInvestigationDb;
GO

SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    ------------------------------------------------------------
    -- 1. Create a sequence for automatically generated investigation IDs,
    --    starting above the highest existing investigation_id to avoid
    --    colliding with rows created before this migration ran.
    ------------------------------------------------------------
    IF OBJECT_ID(N'dbo.investigation_id_seq', N'SO') IS NULL
    BEGIN
        DECLARE @seq_start INT =
            (SELECT ISNULL(MAX(investigation_id), 9999) + 1 FROM dbo.investigations);

        IF @seq_start < 10000
            SET @seq_start = 10000;

        DECLARE @create_seq_sql NVARCHAR(MAX) = N'
            CREATE SEQUENCE dbo.investigation_id_seq
                AS INT
                START WITH ' + CAST(@seq_start AS NVARCHAR(20)) + N'
                INCREMENT BY 1;
        ';
        EXEC sp_executesql @create_seq_sql;
    END;

    ------------------------------------------------------------
    -- 1b. If the sequence already existed, make sure its current
    --     position is above the highest stored investigation_id.
    ------------------------------------------------------------
    DECLARE @max_investigation_id INT =
        (SELECT ISNULL(MAX(investigation_id), 9999) FROM dbo.investigations);

    DECLARE @seq_current_value SQL_VARIANT =
        (SELECT current_value FROM sys.sequences WHERE object_id = OBJECT_ID(N'dbo.investigation_id_seq'));

    IF @seq_current_value IS NOT NULL
       AND CAST(@seq_current_value AS INT) <= @max_investigation_id
    BEGIN
        DECLARE @seq_restart INT = @max_investigation_id + 1;

        IF @seq_restart < 10000
            SET @seq_restart = 10000;

        DECLARE @restart_seq_sql NVARCHAR(MAX) = N'
            ALTER SEQUENCE dbo.investigation_id_seq
                RESTART WITH ' + CAST(@seq_restart AS NVARCHAR(20)) + N';
        ';
        EXEC sp_executesql @restart_seq_sql;
    END;

    ------------------------------------------------------------
    -- 2. Add provider as nullable temporarily.
    ------------------------------------------------------------
    IF COL_LENGTH(N'dbo.investigations', N'provider') IS NULL
    BEGIN
        ALTER TABLE dbo.investigations
        ADD provider NVARCHAR(30) NULL;
    END;

    ------------------------------------------------------------
    -- 3. Populate missing provider values.
    ------------------------------------------------------------
    EXEC sp_executesql N'
        UPDATE dbo.investigations
        SET provider = N''mock''
        WHERE provider IS NULL;
    ';

    ------------------------------------------------------------
    -- 3b. Normalize any provider values outside the allowed set.
    ------------------------------------------------------------
    EXEC sp_executesql N'
        UPDATE dbo.investigations
        SET provider = N''mock''
        WHERE provider IS NULL
           OR provider NOT IN (N''mock'', N''copilot_studio'', N''gemini'');
    ';

    ------------------------------------------------------------
    -- 4. Make provider required (dynamic SQL: column may have been
    --    added earlier in this same batch).
    ------------------------------------------------------------
    EXEC sp_executesql N'
        ALTER TABLE dbo.investigations
        ALTER COLUMN provider NVARCHAR(30) NOT NULL;
    ';

    ------------------------------------------------------------
    -- 5. Add context_snapshot as nullable temporarily.
    ------------------------------------------------------------
    IF COL_LENGTH(N'dbo.investigations', N'context_snapshot') IS NULL
    BEGIN
        ALTER TABLE dbo.investigations
        ADD context_snapshot NVARCHAR(MAX) NULL;
    END;

    ------------------------------------------------------------
    -- 6. Populate missing context_snapshot values.
    ------------------------------------------------------------
    EXEC sp_executesql N'
        UPDATE dbo.investigations
        SET context_snapshot = N''{}''
        WHERE context_snapshot IS NULL;
    ';

    ------------------------------------------------------------
    -- 6b. Normalize any context_snapshot values that are not valid JSON.
    ------------------------------------------------------------
    EXEC sp_executesql N'
        UPDATE dbo.investigations
        SET context_snapshot = N''{}''
        WHERE context_snapshot IS NULL
           OR ISJSON(context_snapshot) <> 1;
    ';

    ------------------------------------------------------------
    -- 7. Make context_snapshot required (dynamic SQL: column may have
    --    been added earlier in this same batch).
    ------------------------------------------------------------
    EXEC sp_executesql N'
        ALTER TABLE dbo.investigations
        ALTER COLUMN context_snapshot NVARCHAR(MAX) NOT NULL;
    ';

    ------------------------------------------------------------
    -- 8. Add response_payload as nullable temporarily.
    ------------------------------------------------------------
    IF COL_LENGTH(N'dbo.investigations', N'response_payload') IS NULL
    BEGIN
        ALTER TABLE dbo.investigations
        ADD response_payload NVARCHAR(MAX) NULL;
    END;

    ------------------------------------------------------------
    -- 9. Populate missing response_payload values.
    ------------------------------------------------------------
    EXEC sp_executesql N'
        UPDATE dbo.investigations
        SET response_payload = N''{}''
        WHERE response_payload IS NULL;
    ';

    ------------------------------------------------------------
    -- 9b. Normalize any response_payload values that are not valid JSON.
    ------------------------------------------------------------
    EXEC sp_executesql N'
        UPDATE dbo.investigations
        SET response_payload = N''{}''
        WHERE response_payload IS NULL
           OR ISJSON(response_payload) <> 1;
    ';

    ------------------------------------------------------------
    -- 10. Make response_payload required (dynamic SQL: column may have
    --     been added earlier in this same batch).
    ------------------------------------------------------------
    EXEC sp_executesql N'
        ALTER TABLE dbo.investigations
        ALTER COLUMN response_payload NVARCHAR(MAX) NOT NULL;
    ';

    ------------------------------------------------------------
    -- 11. Add default constraints for the new columns (dynamic SQL:
    --     columns may have been added earlier in this same batch).
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'DF_investigations_provider'
    )
    BEGIN
        EXEC sp_executesql N'
            ALTER TABLE dbo.investigations
            ADD CONSTRAINT DF_investigations_provider
            DEFAULT (N''mock'') FOR provider;
        ';
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'DF_investigations_context_snapshot'
    )
    BEGIN
        EXEC sp_executesql N'
            ALTER TABLE dbo.investigations
            ADD CONSTRAINT DF_investigations_context_snapshot
            DEFAULT (N''{}'') FOR context_snapshot;
        ';
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'DF_investigations_response_payload'
    )
    BEGIN
        EXEC sp_executesql N'
            ALTER TABLE dbo.investigations
            ADD CONSTRAINT DF_investigations_response_payload
            DEFAULT (N''{}'') FOR response_payload;
        ';
    END;

    ------------------------------------------------------------
    -- 12. Add investigation_id automatic default.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.default_constraints dc
        INNER JOIN sys.columns c
            ON c.object_id = dc.parent_object_id
           AND c.column_id = dc.parent_column_id
        WHERE dc.parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND c.name = N'investigation_id'
    )
    BEGIN
        ALTER TABLE dbo.investigations
        ADD CONSTRAINT DF_investigations_investigation_id
        DEFAULT (NEXT VALUE FOR dbo.investigation_id_seq)
        FOR investigation_id;
    END;

    ------------------------------------------------------------
    -- 13. Add provider and JSON check constraints (dynamic SQL:
    --     columns may have been added earlier in this same batch).
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'CK_investigations_provider'
    )
    BEGIN
        EXEC sp_executesql N'
            ALTER TABLE dbo.investigations
            ADD CONSTRAINT CK_investigations_provider
            CHECK (provider IN (N''mock'', N''copilot_studio'', N''gemini''));
        ';
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'CK_investigations_context_snapshot_json'
    )
    BEGIN
        EXEC sp_executesql N'
            ALTER TABLE dbo.investigations
            ADD CONSTRAINT CK_investigations_context_snapshot_json
            CHECK (ISJSON(context_snapshot) = 1);
        ';
    END;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'CK_investigations_response_payload_json'
    )
    BEGIN
        EXEC sp_executesql N'
            ALTER TABLE dbo.investigations
            ADD CONSTRAINT CK_investigations_response_payload_json
            CHECK (ISJSON(response_payload) = 1);
        ';
    END;

    ------------------------------------------------------------
    -- 14. Add lookup index.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'IX_investigations_alert_created'
    )
    BEGIN
        CREATE INDEX IX_investigations_alert_created
            ON dbo.investigations (alert_id, created_at);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO

------------------------------------------------------------
-- Verification queries (read-only; run manually after the migration).
------------------------------------------------------------
-- Confirm the sequence exists and check its current position.
-- SELECT * FROM sys.sequences WHERE name = N'investigation_id_seq';

-- Confirm the new columns, defaults, and nullability.
-- SELECT c.name, c.is_nullable, dc.definition
-- FROM sys.columns c
-- LEFT JOIN sys.default_constraints dc
--     ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
-- WHERE c.object_id = OBJECT_ID(N'dbo.investigations')
--   AND c.name IN (N'investigation_id', N'provider', N'context_snapshot', N'response_payload');

-- Confirm the check constraints exist.
-- SELECT name, definition FROM sys.check_constraints
-- WHERE parent_object_id = OBJECT_ID(N'dbo.investigations');

-- Confirm the index exists.
-- SELECT name FROM sys.indexes
-- WHERE object_id = OBJECT_ID(N'dbo.investigations')
--   AND name = N'IX_investigations_alert_created';

-- Confirm every existing row now has valid provider/JSON values and no rows were lost.
-- SELECT COUNT(*) AS total_rows,
--        SUM(CASE WHEN provider IS NULL THEN 1 ELSE 0 END) AS null_provider,
--        SUM(CASE WHEN ISJSON(context_snapshot) <> 1 THEN 1 ELSE 0 END) AS bad_context_snapshot,
--        SUM(CASE WHEN ISJSON(response_payload) <> 1 THEN 1 ELSE 0 END) AS bad_response_payload
-- FROM dbo.investigations;
