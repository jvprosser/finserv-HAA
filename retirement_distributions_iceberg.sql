-- =============================================================================
-- Retirement distributions — Cloudera Hive + Apache Iceberg DDL
-- =============================================================================
-- Engine target : CDP Hive / Impala Iceberg v2
-- Database      : retirement_distributions
-- Demo cases    : 7001 termination, 7002 hardship substantiation, 7003 RMD,
--                 7011–7017 hardship / ERISA / SECURE 2.0 / QDRO
--
-- JSON contract (Studio / MCP): packs/retirement_distributions/fixtures/
-- CREATE TABLE shape: not EXTERNAL; COMMENT before PARTITIONED BY SPEC.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS retirement_distributions;
USE retirement_distributions;


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_request (
  distribution_request_id   BIGINT    COMMENT 'PK. Studio claim_id / case_id (7001, 7002, 7003).',
  request_status_code       STRING    COMMENT 'OPEN | CLOSED.',
  distribution_type_code    STRING    COMMENT 'TERMINATION | HARDSHIP | RMD | SECURE20_EMERGENCY.',
  plan_id                   STRING    COMMENT 'Plan identifier (e.g. 401k-alpha).',
  participant_id            STRING    COMMENT 'Participant business key.',
  hold_or_aml_flag          BOOLEAN   COMMENT 'True when request is on hold / AML review.',
  requested_amount          DECIMAL(18,2) COMMENT 'Requested distribution amount.',
  created_at                TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Retirement distribution request spine (one row per Studio claim_id).'
PARTITIONED BY SPEC (
  request_status_code
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionRequest',
  'llm.primary_key' = 'distribution_request_id',
  'llm.grain' = 'one distribution request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_exception (
  exception_id              STRING    COMMENT 'PK. Exception business key (e.g. EX-7002).',
  distribution_request_id   BIGINT    COMMENT 'FK -> distribution_request.distribution_request_id.',
  reason_code               STRING    COMMENT 'HARDSHIP_SUBSTANTIATION_MISSING | HOLD_AML | other.',
  queue                     STRING    COMMENT 'Exception queue name (e.g. ExceptionQueue).',
  required_docs             STRING    COMMENT 'JSON array of required document codes.',
  created_at                TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Open exception on a distribution request (Exception Queue view).'
PARTITIONED BY SPEC (
  reason_code
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionException',
  'llm.primary_key' = 'exception_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one exception on a request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_rmd (
  rmd_id                    BIGINT    COMMENT 'PK. Surrogate RMD assessment id.',
  distribution_request_id   BIGINT    COMMENT 'FK -> distribution_request.distribution_request_id.',
  tax_year                  INT       COMMENT 'RMD tax year.',
  required_amount           DECIMAL(18,2) COMMENT 'Required minimum distribution amount.',
  paid_amount               DECIMAL(18,2) COMMENT 'Amount already paid for the tax year.',
  shortfall_amount          DECIMAL(18,2) COMMENT 'required_amount - paid_amount.',
  deadline                  DATE      COMMENT 'RMD deadline date.',
  created_at                TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'RMD required vs paid amounts for a distribution request (RMD Ops view).'
PARTITIONED BY SPEC (
  tax_year
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionRmd',
  'llm.primary_key' = 'rmd_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one RMD assessment on a request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_plan (
  plan_id                       STRING    COMMENT 'PK. Plan identifier (e.g. 401k-alpha).',
  plan_subject_to_qjsa          BOOLEAN   COMMENT 'True when ERISA QJSA / spousal consent applies.',
  plan_mandates_loan_exhaustion BOOLEAN   COMMENT 'True when available loans must be exhausted before hardship.',
  created_at                    TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Plan-level ERISA / hardship loan rules.'
PARTITIONED BY SPEC (
  plan_id
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionPlan',
  'llm.primary_key' = 'plan_id',
  'llm.grain' = 'one plan'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_participant (
  participant_id                STRING    COMMENT 'PK. Participant business key.',
  participant_marital_status    STRING    COMMENT 'SINGLE | MARRIED | DIVORCED | WIDOWED.',
  spousal_consent_verified      BOOLEAN   COMMENT 'True when signed spousal consent is on file.',
  created_at                    TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Participant marital / QJSA consent facts.'
PARTITIONED BY SPEC (
  participant_marital_status
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionParticipant',
  'llm.primary_key' = 'participant_id',
  'llm.grain' = 'one participant'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_hardship (
  distribution_request_id             BIGINT    COMMENT 'PK/FK -> distribution_request.distribution_request_id.',
  hardship_category                   STRING    COMMENT 'IRS Safe Harbor category code.',
  documented_financial_need_amount    DECIMAL(18,2) COMMENT 'Verified obligation total.',
  estimated_tax_withholding_amount    DECIMAL(18,2) COMMENT 'Estimated withholding added to need.',
  has_participant_self_certified      BOOLEAN   COMMENT 'SECURE 2.0 self-certification of heavy need.',
  requires_substantiation_audit       BOOLEAN   COMMENT 'Plan still requires documentary audit.',
  created_at                          TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Hardship facts for playbook CEL (category, amounts, self-cert).'
PARTITIONED BY SPEC (
  hardship_category
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionHardship',
  'llm.primary_key' = 'distribution_request_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one hardship row per request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_loan (
  distribution_request_id       BIGINT    COMMENT 'PK/FK -> distribution_request.distribution_request_id.',
  available_plan_loan_capacity  DECIMAL(18,2) COMMENT 'Remaining loan capacity before hardship.',
  outstanding_loan_balance      DECIMAL(18,2) COMMENT 'Current plan loan balance.',
  max_loan_amount               DECIMAL(18,2) COMMENT 'Plan maximum loan amount.',
  created_at                    TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Plan loan capacity for hardship loan-exhaustion probe.'
PARTITIONED BY SPEC (
  distribution_request_id
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionLoan',
  'llm.primary_key' = 'distribution_request_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one loan summary per request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_qdro (
  qdro_id                     BIGINT    COMMENT 'PK. Surrogate QDRO id.',
  distribution_request_id     BIGINT    COMMENT 'FK -> distribution_request.distribution_request_id.',
  is_active                   BOOLEAN   COMMENT 'True when the QDRO hold is in force.',
  order_status_code           STRING    COMMENT 'ACTIVE | PENDING | RELEASED.',
  alternate_payee_name        STRING    COMMENT 'Alternate payee display name (no SSN).',
  hold_reason                 STRING    COMMENT 'Business reason for the hold.',
  created_at                  TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'QDRO hold on a distribution request (Legal / Compliance view).'
PARTITIONED BY SPEC (
  order_status_code
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionQdro',
  'llm.primary_key' = 'qdro_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one QDRO on a request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_court_order (
  court_order_id              BIGINT    COMMENT 'PK. Surrogate court-order id.',
  distribution_request_id     BIGINT    COMMENT 'FK -> distribution_request.distribution_request_id.',
  docket_number               STRING    COMMENT 'Court docket number.',
  status_code                 STRING    COMMENT 'PENDING | CLOSED.',
  created_at                  TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Pending court orders on a distribution request (QDRO / legal probe).'
PARTITIONED BY SPEC (
  status_code
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionCourtOrder',
  'llm.primary_key' = 'court_order_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one court order on a request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_emergency_ytd (
  distribution_request_id     BIGINT    COMMENT 'PK/FK -> distribution_request.distribution_request_id.',
  tax_year                    INT       COMMENT 'Calendar year of the emergency count.',
  prior_count                 INT       COMMENT 'Prior SECURE 2.0 emergency distributions this year.',
  created_at                  TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Year-to-date emergency distribution count (SECURE 2.0 § 115).'
PARTITIONED BY SPEC (
  tax_year
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionEmergencyYtd',
  'llm.primary_key' = 'distribution_request_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one YTD emergency count per request'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.distribution_outbound_notice (
  notice_id                   BIGINT    COMMENT 'PK. Deterministic id from run_id + claim_id.',
  distribution_request_id     BIGINT    COMMENT 'FK -> distribution_request.distribution_request_id.',
  purpose_code                STRING    COMMENT 'REQUEST_SELF_CERTIFICATION | other.',
  channel_code                STRING    COMMENT 'LETTER | EMAIL | SMS.',
  body_text                   STRING    COMMENT 'Notice body (no SSN).',
  run_id                      STRING    COMMENT 'Agent Studio / workflow run id.',
  created_at                  TIMESTAMP COMMENT 'Row creation timestamp.'
)
COMMENT 'Outbound client notice written by send_client_notice (no carrier send).'
PARTITIONED BY SPEC (
  purpose_code
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions',
  'llm.ontology_class' = 'DistributionOutboundNotice',
  'llm.primary_key' = 'notice_id',
  'llm.foreign_keys' = 'distribution_request_id->distribution_request.distribution_request_id',
  'llm.grain' = 'one outbound notice'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.agent_run_audit (
  run_id                    STRING    COMMENT 'PK part. Agent Studio / workflow run id.',
  event_ts                  TIMESTAMP COMMENT 'Event timestamp UTC.',
  claim_id                  STRING    COMMENT 'Studio claim_id / case_id as string.',
  event_type                STRING    COMMENT 'ROUTE_DECISION|WORKER_START|WORKER_END|ERROR|STOP.',
  next_step                 STRING    COMMENT 'Playbook step id.',
  agent_role                STRING    COMMENT 'Worker role id.',
  lane                      STRING    COMMENT 'Routing lane.',
  needs_llm                 BOOLEAN   COMMENT 'Whether LLM tools were allowed.',
  terminal                  BOOLEAN   COMMENT 'Whether router marked terminal.',
  reason_probe_ids          STRING    COMMENT 'JSON array of probe ids.',
  payload_json              STRING    COMMENT 'Full decision / event JSON.'
)
COMMENT 'Append-only agent routing/worker audit events (Impala table-append).'
PARTITIONED BY SPEC (
  run_id
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions_agent',
  'llm.ontology_class' = 'AgentRunAuditEvent'
);


CREATE TABLE IF NOT EXISTS retirement_distributions.agent_run_evidence (
  run_id                    STRING    COMMENT 'FK/logical -> agent_run_audit.run_id.',
  evidence_ts               TIMESTAMP COMMENT 'Evidence timestamp UTC.',
  claim_id                  STRING    COMMENT 'Studio claim_id / case_id as string.',
  evidence_type             STRING    COMMENT 'VALIDATION|WORKER_OUTPUT|other.',
  probe_id                  STRING    COMMENT 'Optional probe id.',
  content_format            STRING    COMMENT 'json|text.',
  content_text              STRING    COMMENT 'Evidence payload.',
  content_uri               STRING    COMMENT 'Optional external URI.'
)
COMMENT 'Evidence artifacts for an agent run. Keep PII out of payloads.'
PARTITIONED BY SPEC (
  run_id
)
STORED BY ICEBERG
STORED AS PARQUET
TBLPROPERTIES (
  'format-version' = '2',
  'llm.domain' = 'retirement_distributions_agent',
  'llm.ontology_class' = 'AgentRunEvidence'
);
