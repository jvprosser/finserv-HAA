  CREATE TABLE IF NOT EXISTS retirement_distributions.yodlee_transactions (
    transaction_id   BIGINT         COMMENT 'Yodlee transaction ID',
    account_id       BIGINT         COMMENT 'Yodlee account ID',
    client_id        STRING         COMMENT 'Client or party key. Rename when the warehouse column is confirmed.',
    posted_date      DATE           COMMENT 'Posted date',
    amount           DECIMAL(18,4)  COMMENT 'Transaction amount',
    base_type        STRING         COMMENT 'CREDIT or DEBIT',
    category         STRING         COMMENT 'Yodlee category',
    description      STRING         COMMENT 'Transaction description',
    merchant_name    STRING         COMMENT 'Merchant or source name',
    status           STRING         COMMENT 'Transaction status'
)
PARTITIONED BY SPEC (days(posted_date))
STORED by ICEBERG
TBLPROPERTIES ('format-version' = '2');
