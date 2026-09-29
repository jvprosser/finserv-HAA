CREATE TABLE IF NOT EXISTS retirement_distributions.yodlee_held_away_accounts (
  -- Core Account Identifiers
    account_id                    BIGINT         COMMENT 'Unique Yodlee account ID (id)',
    provider_account_id           BIGINT         COMMENT 'Yodlee provider account ID',
    provider_id                   STRING         COMMENT 'Financial institution provider ID',
    provider_name                 STRING         COMMENT 'Financial institution name',
    account_number                STRING         COMMENT 'Masked account number',
    account_name                  STRING         COMMENT 'Account name assigned by institution',
    displayed_name                STRING         COMMENT 'Display name configured for user',

  -- Classification & Status
    container                     STRING         COMMENT 'Yodlee container type (bank, creditCard, investment, loan, etc.)',
    account_type                  STRING         COMMENT 'Account sub-type (CHECKING, SAVINGS, IRA, 401K, 403B, OTHER, etc.)',
    account_status                STRING         COMMENT 'Account status (ACTIVE, INACTIVE, etc.)',
    user_classification           STRING         COMMENT 'Classification (PERSONAL, BUSINESS)',
    classification                STRING         COMMENT 'Account classification',
    aggregation_source            STRING         COMMENT 'Source of aggregation (USER, SYSTEM)',
    is_asset                      BOOLEAN        COMMENT 'Flag indicating if account represents an asset',
    is_manual                     BOOLEAN        COMMENT 'Flag indicating if account was added manually',
    include_in_net_worth          BOOLEAN        COMMENT 'Flag for net worth inclusion calculations',

  -- Core Balances
    balance_amount                DECIMAL(18,4)  COMMENT 'Total balance amount',
    balance_currency              STRING         COMMENT 'Currency code for balance',
    current_balance_amount        DECIMAL(18,4)  COMMENT 'Current balance amount',
    current_balance_currency      STRING         COMMENT 'Currency code for current balance',
    available_balance_amount      DECIMAL(18,4)  COMMENT 'Available balance amount',
    available_balance_currency    STRING         COMMENT 'Currency code for available balance',
    running_balance_amount        DECIMAL(18,4)  COMMENT 'Running balance amount',
    running_balance_currency      STRING         COMMENT 'Currency code for running balance',

  -- Credit & Loan Attributes (creditCard / loan containers)
    available_credit_amount       DECIMAL(18,4)  COMMENT 'Available credit line amount',
    available_credit_currency     STRING         COMMENT 'Currency code for available credit',
    total_credit_line_amount      DECIMAL(18,4)  COMMENT 'Total credit line limit',
    total_credit_line_currency    STRING         COMMENT 'Currency code for total credit line',
    available_cash_amount         DECIMAL(18,4)  COMMENT 'Available cash advance amount',
    available_cash_currency       STRING         COMMENT 'Currency code for available cash',
    total_cash_limit_amount       DECIMAL(18,4)  COMMENT 'Total cash advance limit',
    total_cash_limit_currency     STRING         COMMENT 'Currency code for cash limit',
    last_payment_amount           DECIMAL(18,4)  COMMENT 'Amount of last payment made',
    last_payment_currency         STRING         COMMENT 'Currency code for last payment',
    last_payment_date             DATE           COMMENT 'Date of last payment',
    apr                           DECIMAL(5,2)   COMMENT 'Annual Percentage Rate',
    cash_apr                      DECIMAL(5,2)   COMMENT 'Cash advance APR',

  -- Investment Container Specific Attributes (401k, 403b, IRA, Brokerage)
  vested_balance_amount         DECIMAL(18,4)  COMMENT 'Vested portion of balance in investment account',
  vested_balance_currency       STRING         COMMENT 'Currency code for vested balance',
  unvested_balance_amount       DECIMAL(18,4)  COMMENT 'Unvested portion of balance in investment account',
  unvested_balance_currency     STRING         COMMENT 'Currency code for unvested balance',
  margin_balance_amount         DECIMAL(18,4)  COMMENT 'Margin balance in investment account',
  margin_balance_currency       STRING         COMMENT 'Currency code for margin balance',
  short_balance_amount          DECIMAL(18,4)  COMMENT 'Short balance in investment account',
  short_balance_currency        STRING         COMMENT 'Currency code for short balance',
  buying_power_amount           DECIMAL(18,4)  COMMENT 'Investment buying power',
  buying_power_currency         STRING         COMMENT 'Currency code for buying power',

  -- Complex Nested Dataset Array
--    dataset                       ARRAY<STRUCT<
--    name: STRING,
--    additional_status: STRING,
--    update_eligibility: STRING,
--    last_updated: TIMESTAMP,
--    last_update_attempt: TIMESTAMP,
--    next_update_scheduled: TIMESTAMP
--    >>             COMMENT 'Yodlee aggregation dataset status metrics',

  -- Timestamps
    created_date                  TIMESTAMP      COMMENT 'Creation timestamp in Yodlee',
    last_updated                  TIMESTAMP      COMMENT 'Last update timestamp in Yodlee',
    ingestion_timestamp           TIMESTAMP      COMMENT 'Timestamp when record was loaded into Iceberg'
    )
    PARTITIONED BY (
    container,
    days(last_updated)
    )
    STORED AS ICEBERG
    TBLPROPERTIES (
    'format-version'='2',
    'write.parquet.compression-codec'='snappy',
    'history.expire.max-snapshot-age-ms'='604800000' -- 7 days retention for snapshots
    );