USE FraudInvestigationDb;
GO

IF OBJECT_ID(N'dbo.customers', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.customers (
        customer_id INT NOT NULL,
        customer_reference NVARCHAR(50) NOT NULL,
        first_name NVARCHAR(100) NOT NULL,
        last_name NVARCHAR(100) NOT NULL,
        email NVARCHAR(255) NULL,
        phone NVARCHAR(50) NULL,
        date_of_birth DATETIME2 NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_customers_created_at DEFAULT SYSUTCDATETIME(),
        is_active BIT NOT NULL CONSTRAINT DF_customers_is_active DEFAULT 1,
        CONSTRAINT PK_customers PRIMARY KEY (customer_id),
        CONSTRAINT UQ_customers_customer_reference UNIQUE (customer_reference)
    );
END;
GO

IF OBJECT_ID(N'dbo.transactions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.transactions (
        transaction_id INT NOT NULL,
        customer_id INT NOT NULL,
        business_transaction_id NVARCHAR(64) NOT NULL,
        transaction_datetime DATETIME2 NOT NULL,
        recorded_customer_reference NVARCHAR(50) NULL,
        amount DECIMAL(12,2) NOT NULL,
        merchant_name NVARCHAR(200) NULL,
        merchant_category NVARCHAR(100) NULL,
        channel NVARCHAR(50) NULL,
        location NVARCHAR(100) NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_transactions_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_transactions PRIMARY KEY (transaction_id),
        CONSTRAINT FK_transactions_customers FOREIGN KEY (customer_id) REFERENCES dbo.customers (customer_id)
    );
END;
GO

IF OBJECT_ID(N'dbo.risk_alert_id_seq', N'SO') IS NULL
BEGIN
    CREATE SEQUENCE dbo.risk_alert_id_seq
        AS INT
        START WITH 6000
        INCREMENT BY 1;
END;
GO

IF OBJECT_ID(N'dbo.risk_alerts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.risk_alerts (
        alert_id INT NOT NULL
            CONSTRAINT DF_risk_alerts_alert_id
            DEFAULT (NEXT VALUE FOR dbo.risk_alert_id_seq),

        transaction_id INT NOT NULL,
        customer_id INT NOT NULL,

        analysis_key NVARCHAR(200) NOT NULL,

        alert_type NVARCHAR(50) NOT NULL,

        risk_score INT NOT NULL
            CONSTRAINT CK_risk_alerts_risk_score
            CHECK (risk_score BETWEEN 0 AND 100),

        severity NVARCHAR(20) NOT NULL
            CONSTRAINT CK_risk_alerts_severity
            CHECK (severity IN (
                N'LOW',
                N'MEDIUM',
                N'HIGH',
                N'CRITICAL'
            )),

        alert_status NVARCHAR(20) NOT NULL
            CONSTRAINT DF_risk_alerts_alert_status
            DEFAULT (N'OPEN')
            CONSTRAINT CK_risk_alerts_alert_status
            CHECK (alert_status IN (
                N'OPEN',
                N'ACKNOWLEDGED',
                N'RESOLVED',
                N'DISMISSED'
            )),

        rule_evidence NVARCHAR(MAX) NOT NULL
            CONSTRAINT DF_risk_alerts_rule_evidence
            DEFAULT (N'[]'),

        notes NVARCHAR(500) NULL,

        created_at DATETIME2 NOT NULL
            CONSTRAINT DF_risk_alerts_created_at
            DEFAULT SYSUTCDATETIME(),

        updated_at DATETIME2 NOT NULL
            CONSTRAINT DF_risk_alerts_updated_at
            DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_risk_alerts
            PRIMARY KEY (alert_id),

        CONSTRAINT UQ_risk_alerts_analysis_key
            UNIQUE (analysis_key),

        CONSTRAINT CK_risk_alerts_rule_evidence_json
            CHECK (ISJSON(rule_evidence) = 1),

        CONSTRAINT FK_risk_alerts_transactions
            FOREIGN KEY (transaction_id)
            REFERENCES dbo.transactions (transaction_id),

        CONSTRAINT FK_risk_alerts_customers
            FOREIGN KEY (customer_id)
            REFERENCES dbo.customers (customer_id)
    );
END;
GO

IF OBJECT_ID(N'dbo.investigation_id_seq', N'SO') IS NULL
BEGIN
    CREATE SEQUENCE dbo.investigation_id_seq
        AS INT
        START WITH 10000
        INCREMENT BY 1;
END;
GO

IF OBJECT_ID(N'dbo.investigations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.investigations (
        investigation_id INT NOT NULL
            CONSTRAINT DF_investigations_investigation_id
            DEFAULT (NEXT VALUE FOR dbo.investigation_id_seq),
        alert_id INT NULL,
        customer_id INT NOT NULL,
        investigation_status NVARCHAR(20) NOT NULL CONSTRAINT CK_investigations_status CHECK (investigation_status IN (N'NEW', N'IN_PROGRESS', N'ON_HOLD', N'CLOSED', N'ESCALATED')),
        priority NVARCHAR(20) NOT NULL CONSTRAINT CK_investigations_priority CHECK (priority IN (N'LOW', N'MEDIUM', N'HIGH', N'CRITICAL')),
        assigned_to NVARCHAR(100) NULL,
        summary NVARCHAR(500) NOT NULL,
        provider NVARCHAR(30) NOT NULL
            CONSTRAINT DF_investigations_provider
            DEFAULT N'mock'
            CONSTRAINT CK_investigations_provider
            CHECK (provider IN (N'mock', N'copilot_studio')),
        context_snapshot NVARCHAR(MAX) NOT NULL
            CONSTRAINT DF_investigations_context_snapshot
            DEFAULT N'{}'
            CONSTRAINT CK_investigations_context_snapshot_json
            CHECK (ISJSON(context_snapshot) = 1),
        response_payload NVARCHAR(MAX) NOT NULL
            CONSTRAINT DF_investigations_response_payload
            DEFAULT N'{}'
            CONSTRAINT CK_investigations_response_payload_json
            CHECK (ISJSON(response_payload) = 1),
        created_at DATETIME2 NOT NULL CONSTRAINT DF_investigations_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_investigations_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_investigations PRIMARY KEY (investigation_id),
        CONSTRAINT FK_investigations_alerts FOREIGN KEY (alert_id) REFERENCES dbo.risk_alerts (alert_id),
        CONSTRAINT FK_investigations_customers FOREIGN KEY (customer_id) REFERENCES dbo.customers (customer_id)
    );
END;
GO

IF OBJECT_ID(N'IX_investigations_alert_created', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_investigations_alert_created
        ON dbo.investigations (alert_id, created_at);
END;
GO

IF OBJECT_ID(N'IX_transactions_transaction_datetime', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_transactions_transaction_datetime
        ON dbo.transactions (transaction_datetime);
END;
GO

IF OBJECT_ID(N'IX_transactions_customer_transaction_time', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_transactions_customer_transaction_time
        ON dbo.transactions (customer_id, transaction_datetime);
END;
GO

IF OBJECT_ID(N'IX_transactions_business_transaction_id', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_transactions_business_transaction_id
        ON dbo.transactions (business_transaction_id);
END;
GO

IF OBJECT_ID(N'IX_transactions_merchant_category', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_transactions_merchant_category
        ON dbo.transactions (merchant_category);
END;
GO

IF OBJECT_ID(N'IX_risk_alerts_lookup', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_risk_alerts_lookup
        ON dbo.risk_alerts (customer_id, alert_status, created_at);
END;
GO

IF OBJECT_ID(N'IX_risk_alerts_transaction_lookup', N'IX') IS NULL
BEGIN
    CREATE INDEX IX_risk_alerts_transaction_lookup
        ON dbo.risk_alerts (transaction_id, alert_status);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_risk_alerts_severity_status'
      AND object_id = OBJECT_ID(N'dbo.risk_alerts')
)
BEGIN
    CREATE INDEX IX_risk_alerts_severity_status
        ON dbo.risk_alerts (
            severity,
            alert_status,
            updated_at
        );
END;
GO
