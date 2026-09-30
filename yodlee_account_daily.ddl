CREATE TABLE IF NOT EXISTS retirement_distributions.yodlee_held_away_accounts_daily (
    as_of_date              DATE           COMMENT 'Business date of this daily snapshot',
    client_id               STRING         COMMENT 'Client or party key. Rename when the warehouse column is confirmed.',
    account_id              BIGINT         COMMENT 'Yodlee account ID',
    container               STRING         COMMENT 'Yodlee container type',
    account_type            STRING         COMMENT 'Account sub-type (CHECKING, SAVINGS, IRA, BROKERAGE, ...)',
    account_status          STRING         COMMENT 'Account status (ACTIVE, INACTIVE, ...)',
    provider_name           STRING         COMMENT 'Financial institution name',
    balance_amount          DECIMAL(18,4)  COMMENT 'Total balance amount on as_of_date',
    balance_currency        STRING         COMMENT 'Currency code for balance',
    is_asset                BOOLEAN        COMMENT 'True when the account is an asset',
    margin_balance_amount   DECIMAL(18,4)  COMMENT 'Margin balance',
    apr                     DECIMAL(5,2)   COMMENT 'Annual percentage rate',
    last_payment_amount     DECIMAL(18,4)  COMMENT 'Amount of the last payment',
    last_payment_date       DATE           COMMENT 'Date of the last payment'
)
PARTITIONED BY SPEC ( as_of_date )
STORED by ICEBERG
TBLPROPERTIES ('format-version' = '2');