USE FraudInvestigationDb;
GO

SET XACT_ABORT ON;
GO

BEGIN TRY
    BEGIN TRANSACTION;

    ------------------------------------------------------------
    -- 1. Drop CK_investigations_provider only if its current definition
    --    does not already permit N'gemini'. Preserves all investigation
    --    rows; does not touch table structure or data.
    ------------------------------------------------------------
    IF EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'CK_investigations_provider'
          AND definition NOT LIKE '%gemini%'
    )
    BEGIN
        ALTER TABLE dbo.investigations
        DROP CONSTRAINT CK_investigations_provider;
    END;

    ------------------------------------------------------------
    -- 2. Add CK_investigations_provider (permitting mock, copilot_studio,
    --    and gemini) if it is not already present -- either because it was
    --    just dropped above, or because it never existed.
    ------------------------------------------------------------
    IF NOT EXISTS (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
          AND name = N'CK_investigations_provider'
    )
    BEGIN
        ALTER TABLE dbo.investigations
        ADD CONSTRAINT CK_investigations_provider
        CHECK (provider IN (N'mock', N'copilot_studio', N'gemini'));
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
-- Confirm the constraint now permits gemini.
-- SELECT name, definition FROM sys.check_constraints
-- WHERE parent_object_id = OBJECT_ID(N'dbo.investigations')
--   AND name = N'CK_investigations_provider';

-- Confirm no rows were lost and every provider value is still valid.
-- SELECT COUNT(*) AS total_rows,
--        SUM(CASE WHEN provider NOT IN (N'mock', N'copilot_studio', N'gemini') THEN 1 ELSE 0 END)
--            AS invalid_provider_rows
-- FROM dbo.investigations;
