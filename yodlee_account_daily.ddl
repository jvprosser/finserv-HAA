CREATE TABLE IF NOT EXISTS retirement_distributions.yodlee_held_away_accounts_daily (
    client_id               STRING         COMMENT 'Client or party key. Rename when the warehouse column is confirmed.',
    account_id              BIGINT         COMMENT 'Yodlee account ID',
    container               STRING         COMMENT 'Yodlee container type',
    account_type            STRING         COMMENT 'Account sub-type (CHECKING, SAVINGS, IRA, BROKERAGE, ...)',
    account_status          STRING         COMMENT 'Account status (ACTIVE, INACTIVE, ...)',
    provider_name           STRING         COMMENT 'Financial institution name',
    ingestion_timestamp     STRING         COMMENT 'NiFi load timestamp. Snapshot day is to_date(ingestion_timestamp).',
    balance_amount          DECIMAL(18,4)  COMMENT 'Total balance amount on the snapshot day',
    balance_currency        STRING         COMMENT 'Currency code for balance',
    is_asset                BOOLEAN        COMMENT 'True when the account is an asset',
    margin_balance_amount   DECIMAL(18,4)  COMMENT 'Margin balance',
    apr                     DECIMAL(5,2)   COMMENT 'Annual percentage rate',
    last_payment_amount     DECIMAL(18,4)  COMMENT 'Amount of the last payment',
    last_payment_date       DATE           COMMENT 'Date of the last payment'
)
PARTITIONED BY SPEC ( ingestion_timestamp )
STORED by ICEBERG
TBLPROPERTIES ('format-version' = '2');