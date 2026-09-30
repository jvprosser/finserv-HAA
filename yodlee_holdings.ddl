CREATE TABLE IF NOT EXISTS retirement_distributions.yodlee_holdings (
    as_of_date      DATE           COMMENT 'Business date of this holdings snapshot',
    account_id      BIGINT         COMMENT 'Yodlee account ID',
    client_id       STRING         COMMENT 'Client or party key. Rename when the warehouse column is confirmed.',
    holding_id      STRING         COMMENT 'Holding identifier',
    description     STRING         COMMENT 'Holding description',
    symbol          STRING         COMMENT 'Ticker or instrument symbol',
    quantity        DECIMAL(18,4)  COMMENT 'Units held',
    value_amount    DECIMAL(18,4)  COMMENT 'Market value',
    holding_type    STRING         COMMENT 'Holding type (stock, CD, mutual fund, ...)'
)
PARTITIONED BY SPEC ( as_of_date )
STORED by ICEBERG
TBLPROPERTIES ('format-version' = '2');