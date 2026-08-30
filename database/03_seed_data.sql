USE FraudInvestigationDb;
GO

SET NOCOUNT ON;

-- Seed some fictional customers with stable IDs so the script can be rerun safely.
MERGE INTO dbo.customers AS target
USING (
    VALUES
        (101, N'CUST-1001', N'Alice', N'Nguyen', N'alice.nguyen@example.com', N'+1-206-555-0101', CONVERT(DATETIME2, '1988-04-12T00:00:00'), 1),
        (102, N'CUST-1002', N'Bob', N'Ramos', N'bob.ramos@example.com', N'+1-312-555-0102', CONVERT(DATETIME2, '1984-11-03T00:00:00'), 1),
        (103, N'CUST-1003', N'Carol', N'Patel', N'carol.patel@example.com', N'+1-512-555-0103', CONVERT(DATETIME2, '1991-02-18T00:00:00'), 1),
        (104, N'CUST-1004', N'Daniel', N'Kim', N'daniel.kim@example.com', N'+1-617-555-0104', CONVERT(DATETIME2, '1979-09-27T00:00:00'), 1)
) AS source (customer_id, customer_reference, first_name, last_name, email, phone, date_of_birth, is_active)
ON target.customer_id = source.customer_id
WHEN MATCHED THEN
    UPDATE SET
        customer_reference = source.customer_reference,
        first_name = source.first_name,
        last_name = source.last_name,
        email = source.email,
        phone = source.phone,
        date_of_birth = source.date_of_birth,
        is_active = source.is_active
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_reference, first_name, last_name, email, phone, date_of_birth, created_at, is_active)
    VALUES (source.customer_id, source.customer_reference, source.first_name, source.last_name, source.email, source.phone, source.date_of_birth, SYSUTCDATETIME(), source.is_active);
GO

-- The transaction seed intentionally includes ordinary activity plus several fraud-pattern anomalies.
-- Anomalies demonstrated: unusually large purchase, repeated transactions, duplicate business_transaction_id,
-- missing merchant, missing merchant category, zero-dollar amount, a customer-reference mismatch,
-- unusual location/channel activity, and otherwise normal retail behavior for comparison.
MERGE INTO dbo.transactions AS target
USING (
    VALUES
        (1001, 101, N'BIZ-OL-1001', CONVERT(DATETIME2, '2026-07-01T09:05:00'), N'CUST-1001', CAST(42.50 AS DECIMAL(12,2)), N'Market Fresh', N'Groceries', N'Mobile', N'Seattle, WA'),
        (1002, 101, N'BIZ-OL-1002', CONVERT(DATETIME2, '2026-07-01T09:42:00'), N'CUST-1001', CAST(18.99 AS DECIMAL(12,2)), N'Coffee Corner', N'Dining', N'Web', N'Seattle, WA'),
        (1003, 101, N'BIZ-OL-1003', CONVERT(DATETIME2, '2026-07-02T15:20:00'), N'CUST-1001', CAST(92.15 AS DECIMAL(12,2)), N'Bookstore', N'Books', N'Store', N'Portland, OR'),
        (1004, 101, N'BIZ-REP-9001', CONVERT(DATETIME2, '2026-07-03T07:10:00'), N'CUST-1001', CAST(15.30 AS DECIMAL(12,2)), N'Fuel Stop', N'Fuel', N'Mobile', N'Seattle, WA'),
        (1005, 101, N'BIZ-REP-9001', CONVERT(DATETIME2, '2026-07-03T07:18:00'), N'CUST-1001', CAST(15.30 AS DECIMAL(12,2)), N'Fuel Stop', N'Fuel', N'Mobile', N'Seattle, WA'),
        (1006, 101, N'BIZ-LARGE-3001', CONVERT(DATETIME2, '2026-07-04T18:33:00'), N'CUST-1001', CAST(95000.00 AS DECIMAL(12,2)), N'Luxury Auto', N'Automotive', N'Store', N'New York, NY'),
        (1007, 101, N'BIZ-MISSING-MERCHANT-01', CONVERT(DATETIME2, '2026-07-05T08:00:00'), N'CUST-1001', CAST(65.00 AS DECIMAL(12,2)), NULL, N'Travel', N'Mobile', N'Seattle, WA'),
        (1008, 101, N'BIZ-MISSING-CAT-01', CONVERT(DATETIME2, '2026-07-05T13:15:00'), N'CUST-1001', CAST(120.40 AS DECIMAL(12,2)), N'Amazon', NULL, N'Web', N'Seattle, WA'),
        (1009, 101, N'BIZ-UNUSUAL-AMT-01', CONVERT(DATETIME2, '2026-07-06T10:25:00'), N'CUST-1001', CAST(0.00 AS DECIMAL(12,2)), N'Digital Goods', N'Technology', N'Web', N'Seattle, WA'),
        (1010, 101, N'BIZ-MISMATCH-01', CONVERT(DATETIME2, '2026-07-07T11:00:00'), N'CUST-9999', CAST(88.25 AS DECIMAL(12,2)), N'Quick Mart', N'Groceries', N'Mobile', N'Seattle, WA'),
        (1011, 102, N'BIZ-OL-2001', CONVERT(DATETIME2, '2026-07-02T12:05:00'), N'CUST-1002', CAST(229.00 AS DECIMAL(12,2)), N'Skyline Hotel', N'Travel', N'Card Present', N'Chicago, IL'),
        (1012, 102, N'BIZ-OL-2002', CONVERT(DATETIME2, '2026-07-02T12:40:00'), N'CUST-1002', CAST(49.00 AS DECIMAL(12,2)), N'Fresh Produce', N'Groceries', N'Mobile', N'Chicago, IL'),
        (1013, 102, N'BIZ-OL-2003', CONVERT(DATETIME2, '2026-07-03T08:11:00'), N'CUST-1002', CAST(18.40 AS DECIMAL(12,2)), N'Transit Pass', N'Transport', N'Card Present', N'Chicago, IL'),
        (1014, 102, N'BIZ-OL-2004', CONVERT(DATETIME2, '2026-07-03T19:05:00'), N'CUST-1002', CAST(320.50 AS DECIMAL(12,2)), N'Northwind Travel', N'Travel', N'Mobile', N'New York, NY'),
        (1015, 102, N'BIZ-OL-2005', CONVERT(DATETIME2, '2026-07-04T13:20:00'), N'CUST-1002', CAST(73.00 AS DECIMAL(12,2)), N'Corner Pharmacy', N'Health', N'Mobile', N'Los Angeles, CA'),
        (1016, 102, N'BIZ-DUP-2044', CONVERT(DATETIME2, '2026-07-06T09:00:00'), N'CUST-1002', CAST(300.00 AS DECIMAL(12,2)), N'Boutique', N'Apparel', N'Web', N'Miami, FL'),
        (1017, 102, N'BIZ-DUP-2044', CONVERT(DATETIME2, '2026-07-06T09:10:00'), N'CUST-1002', CAST(300.00 AS DECIMAL(12,2)), N'Boutique', N'Apparel', N'Web', N'Miami, FL'),
        (1018, 102, N'BIZ-UNUSUAL-LOC-01', CONVERT(DATETIME2, '2026-07-07T04:22:00'), N'CUST-1002', CAST(44.90 AS DECIMAL(12,2)), N'Remote Fuel', N'Fuel', N'ATM', N'Riyadh, SA'),
        (1019, 103, N'BIZ-OL-3001', CONVERT(DATETIME2, '2026-07-08T10:00:00'), N'CUST-1003', CAST(65.80 AS DECIMAL(12,2)), N'Pet Supply Co', N'Pet Care', N'Mobile', N'Austin, TX'),
        (1020, 103, N'BIZ-OL-3002', CONVERT(DATETIME2, '2026-07-08T10:18:00'), N'CUST-1003', CAST(102.10 AS DECIMAL(12,2)), N'Electric Works', N'Home Improvement', N'Web', N'Austin, TX'),
        (1021, 103, N'BIZ-OL-3003', CONVERT(DATETIME2, '2026-07-09T17:40:00'), N'CUST-1003', CAST(18.20 AS DECIMAL(12,2)), N'Cafe Nord', N'Dining', N'Mobile', N'Seattle, WA'),
        (1022, 103, N'BIZ-OL-3004', CONVERT(DATETIME2, '2026-07-09T21:30:00'), N'CUST-1003', CAST(41.95 AS DECIMAL(12,2)), N'Grocery Outlet', N'Groceries', N'Web', N'Austin, TX'),
        (1023, 103, N'BIZ-OL-3005', CONVERT(DATETIME2, '2026-07-10T06:55:00'), N'CUST-1003', CAST(186.00 AS DECIMAL(12,2)), N'Airline Booking', N'Travel', N'Card Present', N'Denver, CO'),
        (1024, 103, N'BIZ-OL-3006', CONVERT(DATETIME2, '2026-07-10T12:15:00'), N'CUST-1003', CAST(12.25 AS DECIMAL(12,2)), N'Library', N'Education', N'Store', N'Austin, TX'),
        (1025, 104, N'BIZ-OL-4001', CONVERT(DATETIME2, '2026-07-11T08:00:00'), N'CUST-1004', CAST(210.00 AS DECIMAL(12,2)), N'Hardware House', N'Home Improvement', N'Store', N'Boston, MA'),
        (1026, 104, N'BIZ-OL-4002', CONVERT(DATETIME2, '2026-07-11T13:10:00'), N'CUST-1004', CAST(58.75 AS DECIMAL(12,2)), N'Cinema Plus', N'Entertainment', N'Mobile', N'Boston, MA'),
        (1027, 104, N'BIZ-OL-4003', CONVERT(DATETIME2, '2026-07-12T18:05:00'), N'CUST-1004', CAST(116.30 AS DECIMAL(12,2)), N'Online Pharmacy', N'Health', N'Web', N'Boston, MA'),
        (1028, 104, N'BIZ-OL-4004', CONVERT(DATETIME2, '2026-07-13T10:55:00'), N'CUST-1004', CAST(347.90 AS DECIMAL(12,2)), N'Luxury Goods', N'Retail', N'Card Present', N'London, UK'),
        (1029, 104, N'BIZ-OL-4005', CONVERT(DATETIME2, '2026-07-13T15:00:00'), N'CUST-1004', CAST(21.50 AS DECIMAL(12,2)), N'Co-op Market', N'Groceries', N'ATM', N'Boston, MA'),
        (1030, 104, N'BIZ-OL-4006', CONVERT(DATETIME2, '2026-07-14T06:45:00'), N'CUST-1004', CAST(820.00 AS DECIMAL(12,2)), N'Frequent Flyer', N'Travel', N'Web', N'London, UK')
) AS source (
    transaction_id,
    customer_id,
    business_transaction_id,
    transaction_datetime,
    recorded_customer_reference,
    amount,
    merchant_name,
    merchant_category,
    channel,
    location
)
ON target.transaction_id = source.transaction_id
WHEN MATCHED THEN
    UPDATE SET
        customer_id = source.customer_id,
        business_transaction_id = source.business_transaction_id,
        transaction_datetime = source.transaction_datetime,
        recorded_customer_reference = source.recorded_customer_reference,
        amount = source.amount,
        merchant_name = source.merchant_name,
        merchant_category = source.merchant_category,
        channel = source.channel,
        location = source.location
WHEN NOT MATCHED THEN
    INSERT (transaction_id, customer_id, business_transaction_id, transaction_datetime, recorded_customer_reference, amount, merchant_name, merchant_category, channel, location, created_at)
    VALUES (source.transaction_id, source.customer_id, source.business_transaction_id, source.transaction_datetime, source.recorded_customer_reference, source.amount, source.merchant_name, source.merchant_category, source.channel, source.location, SYSUTCDATETIME());
GO

-- Seed a few alerts linked to the most suspicious transactions. These are intentionally small in count
-- and rerunnable by stable ID; they do not duplicate on subsequent runs.
MERGE INTO dbo.risk_alerts AS target
USING (
    VALUES
        (5001, 1006, 101, N'LARGE_TRANSACTION', 94, N'CRITICAL', N'OPEN', N'Large purchase exceeded the customer’s normal spending range and was outside the expected merchant pattern.'),
        (5002, 1010, 101, N'CUSTOMER_REFERENCE_MISMATCH', 72, N'MEDIUM', N'ACKNOWLEDGED', N'Recorded customer reference did not match the account used for the transaction.'),
        (5003, 1018, 102, N'UNUSUAL_LOCATION', 83, N'HIGH', N'OPEN', N'ATM transaction from a foreign location is unusual for this customer profile.')
) AS source (alert_id, transaction_id, customer_id, alert_type, risk_score, severity, alert_status, notes)
ON target.alert_id = source.alert_id
WHEN MATCHED THEN
    UPDATE SET
        transaction_id = source.transaction_id,
        customer_id = source.customer_id,
        alert_type = source.alert_type,
        risk_score = source.risk_score,
        severity = source.severity,
        alert_status = source.alert_status,
        notes = source.notes
WHEN NOT MATCHED THEN
    INSERT (alert_id, transaction_id, customer_id, alert_type, risk_score, severity, alert_status, created_at, notes)
    VALUES (source.alert_id, source.transaction_id, source.customer_id, source.alert_type, source.risk_score, source.severity, source.alert_status, SYSUTCDATETIME(), source.notes);
GO
