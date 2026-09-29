
### 0. Contributions stopped over 90 days

* **What it detects:** Contributions to a held-away account have stopped for over 90 days.
* **Derived Event:** `CONTRIBUTIONS_STOPPED_OVER_90_DAYS`
* **Business Opportunity:** Triggers a proactive client notification via Salesforce/mobile app asking them to re-authenticate their external institution credentials, ensuring continuous portfolio visibility and accurate wealth reporting.

### 1. Significant Non-TIAA Asset Transfer or Liquidations

* **What it detects:** A large decrease in a held-away brokerage, IRA, or checking account balance without a corresponding reinvestment.
* **Derived Event:** `HELDAWAY_LIQUIDATION_DETECTED`
* **Business Opportunity:** Alerts TIAA advisors that a client has cash sitting uninvested or has liquidated external positions, creating an immediate opportunity to offer managed portfolio options or deposit solutions.

### 2. High-Yield Savings or Competitor Deposit Growth

* **What it detects:** Recurring, growing transfers flowing into a competing external institution or high-yield savings account (HYSA).
* **Derived Event:** `COMPETITOR_OUTFLOW_TREND`
* **Business Opportunity:** Prompts an automated advisor task or targeted marketing campaign to offer TIAA’s competitive deposit rates, cash management accounts, or fixed-income products before more capital leaves.

### 3. Early Retirement or Pension Access Events

* **What it detects:** The first lump-sum or recurring deposit coming from an external pension provider, Social Security Administration, or external annuity provider.
* **Derived Event:** `RETIREMENT_INCOME_COMMENCED`
* **Business Opportunity:** Flags that a client has officially entered the decumulation phase, triggering an advisor consultation for tax-efficient withdrawal strategies, guaranteed income solutions (annuities), or estate planning.

### 4. Direct Payroll Inflow Change (Career / Job Shift)

* **What it detects:** A change in the source or entity name associated with regular direct deposit transactions in checking/savings accounts.
* **Derived Event:** `EMPLOYMENT_PROVIDER_CHANGED`
* **Business Opportunity:** Complements 401k monitoring by confirming a job change *before* rollover decisions are finalized, allowing TIAA advisors to reach out early regarding 401k/403b consolidation and benefit transfers.

### 5. Yodlee Consent / Account Disconnection Status Updates

* **What it detects:** Yodlee webhooks (`OB_ACCOUNT_STATUS_UPDATES` or `OB_CONSENT`) firing when a user revokes consent, edits credentials, or marks an account as closed.
* **Derived Event:** `HELDAWAY_DATA_CONNECTION_LOST`
* **Business Opportunity:** Triggers a proactive client notification via Salesforce/mobile app asking them to re-authenticate their external institution credentials, ensuring continuous portfolio visibility and accurate wealth reporting.

Beyond monitoring 401k contribution drops, your Flink stream can derive several other wealth management events from Yodlee transaction and balance streams:

* **Matured Certificate of Deposit (CD) or Fixed-Term Asset**
* **Detection:** A sudden lump-sum inflow into a held-away checking/savings account originating from an external bank's time deposit or CD product.
* **Derived Event:** `HELDAWAY_CD_MATURED`
* **Action:** Triggers an automated advisor task to offer higher-yield TIAA fixed-income or annuity alternatives before the customer auto-renews at the external institution.


* **529 / Education Fund Withdrawal or Inflow Pattern**
* **Detection:** Recurring outbound transfers to state 529 plans or sudden tuition/higher-education debits from held-away accounts.
* **Derived Event:** `EDUCATION_EXPENSE_PHASE_STARTED`
* **Action:** Prompts advisors to engage the client regarding college wealth planning, tuition liquidity strategies, or wealth transfer options for family dependents.


* **Held-Away Margin or Debt Stress Signal**
* **Detection:** A series of large, sudden interest payments or line-of-credit debits tied to held-away margin accounts or personal lines of credit.
* **Derived Event:** `HIGH_COST_DEBT_LEVERAGE_DETECTED`
* **Action:** Flags an opportunity for wealth advisors to propose asset-backed lending, portfolio-backed lines of credit, or debt-consolidation strategies.


* **Real Estate Transaction / Mortgage Payoff**
* **Detection:** Either a massive wire debit/credit indicating a home purchase/sale, or the abrupt cessation of recurring monthly mortgage payments to an external lender.
* **Derived Event:** `REAL_ESTATE_LIQUIDITY_EVENT`
* **Action:** Alerts TIAA real estate and private wealth teams to offer real asset investment solutions, estate planning updates, or tax-loss harvesting advice following the property event.


* **Excess Idle Cash Accumulation**
* **Detection:** A user's held-away low-yield checking or traditional savings account balance exceeding a specific threshold (e.g., maintaining over $100,000 for 90+ days).
* **Derived Event:** `IDLE_CASH_DRAG_IDENTIFIED`
* **Action:** Triggers a campaign or personalized outreach suggesting active cash management, money market funds, or dollar-cost averaging into a TIAA managed portfolio.