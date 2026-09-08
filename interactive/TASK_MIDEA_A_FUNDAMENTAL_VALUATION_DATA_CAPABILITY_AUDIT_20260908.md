# TASK: Midea A — Fundamental / Valuation Point-in-Time Data Capability Audit

Date: 2026-09-08
Based on accepted review: `interactive/REVIEW_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md`
State: **AUTHORIZED**
Target: 美的集团 A股 `000333.SZ`
Nature: **data-capability / research only**

## 1. Goal

Two frozen technical ML challengers are now accepted:

```text
V1 price/vol only          -> does not beat locked MA OOS
V2 + volume/CSI300 context -> CONTEXT_FEATURES_HURT
```

Do **not** continue stacking technical features or tuning LightGBM.

The next gate is to determine whether the existing local environment can support a genuinely different information source — **point-in-time fundamentals and valuation** — without look-ahead.

This task is an audit and data-lineage task only. It must answer:

> Can local XtQuant/MiniQMT provide enough historical financial/valuation information, with reliable historical availability timestamps, to build a leakage-safe fundamental challenger for Midea?

No ML model is authorized in this task.

## 2. Capability gate — inspect local installed APIs first

Inspect the existing installed XtQuant/MiniQMT capability and record exact APIs/modules actually available for historical financial data, for example any installed equivalents of:

```text
xtdata.download_financial_data
xtdata.get_financial_data
instrument/security detail APIs
historical market/valuation fields if available
```

Do not assume these names exist; inspect the installed environment/source and report the exact callable API names/signatures actually used.

Record:

```text
XtQuant import path / version or identifiable package metadata
financial API names
financial table/category names
available date fields
available statement fields
valuation/market-cap fields if any
```

Do not modify `D:\veighna_studio`.

## 3. Hard point-in-time requirement

A financial observation is safe for trading date `t` only if the environment exposes a reliable historical **availability/disclosure timestamp** showing the data was public by `t`.

Acceptable concepts include exact installed equivalents of:

```text
announcement_date
publish_date
disclosure_date
actual_publication_time
```

A fiscal/report period such as:

```text
2024-12-31
2025Q1
report_date
end_date
```

is **not** an availability timestamp by itself.

Hard rule:

```text
NEVER map a financial record to a trading date using report period alone.
```

If the local data exposes values but does not expose a trustworthy historical availability timestamp, classify:

```text
BLOCKED_FOR_PIT_FUNDAMENTALS
```

and do not fabricate a daily as-of panel.

## 4. Restatement / revision risk — mandatory audit

Historical statement databases often expose the latest restated value for an old quarter. That can create hidden look-ahead even if a report date exists.

Inspect whether the local source exposes enough information to distinguish:

```text
first disclosed value
later corrected/restated value
revision/publication timestamp
```

For at least several Midea report periods, inspect whether multiple historical versions exist or whether the API appears to return only one latest snapshot.

Choose one evidence label:

```text
REVISION_SAFE
REVISION_METADATA_AVAILABLE_BUT_NEEDS_POLICY
LATEST_SNAPSHOT_ONLY_RISK
INSUFFICIENT_EVIDENCE
```

If only latest-restated historical values are available with no revision history, do not call the data fully leakage-safe. State the limitation explicitly.

## 5. Required field inventory

Audit availability and coverage for the following concepts. Use exact local field names and table names; do not invent fields.

### 5.1 Income / profitability

Try to locate historical equivalents of:

```text
revenue / operating revenue
net profit attributable to parent
operating profit
gross profit or cost fields sufficient to derive gross margin
```

### 5.2 Cash flow

Try to locate:

```text
operating cash flow
capital expenditure or investing cash-flow components if available
```

### 5.3 Balance sheet

Try to locate:

```text
total assets
total liabilities
shareholders' equity / equity attributable to parent
cash / monetary funds
```

### 5.4 Share / capitalization data

Try to locate point-in-time historical equivalents of:

```text
total shares
float shares
market capitalization
```

### 5.5 Valuation

Audit whether local historical data provides point-in-time:

```text
PE / PE-TTM
PB
PS
EV or fields sufficient to derive it
 dividend yield if available
```

If valuation ratios are unavailable but can in principle be derived from point-in-time financials + unadjusted historical price + historical shares, report that as `DERIVABLE`, but **do not silently derive with back-adjusted price** in this audit.

## 6. Coverage audit

Target history:

```text
2014-01-01 .. 2026-09-04
```

For every available financial table/category used, report:

```text
first report period
last report period
record count
number of distinct fiscal periods
number of records with availability timestamp
number missing availability timestamp
quarterly vs annual coverage
```

Also report obvious gaps.

Do not fill missing quarters.

## 7. If PIT-safe timestamps exist: build a minimal as-of proof panel

Only if the hard point-in-time gate passes, build a minimal proof-of-concept daily as-of mapping under `work/`.

Use Midea trading dates as master dates.

For each trading date `t`:

```text
select only financial records whose historical availability timestamp <= t
```

At minimum demonstrate 3-5 raw financial fields with no transformation/optimization.

The proof panel is for lineage verification only; do not fit a model and do not evaluate returns.

For several manually selected disclosure boundaries, report:

```text
trading day before disclosure -> old financial record
first eligible trading day after disclosure -> new financial record
```

If disclosure occurs after market close and exact time-of-day is available, the new record must not become usable until the next tradable session. If only a date (not time) is available, use a conservative policy:

```text
available from next trading day
```

and document it.

## 8. Leakage tests required if panel is built

Add deterministic tests proving:

```text
[ ] report period alone never activates a record
[ ] observation before disclosure cannot see the new quarter
[ ] observation after allowed disclosure boundary can see it
[ ] same-day disclosure with unknown time becomes usable next trading day
[ ] future corrections/restatements do not overwrite earlier as-of state unless revision metadata proves they were known then
[ ] missing disclosure timestamp is excluded/fail-closed
[ ] no backward fill of future fundamentals
[ ] Midea trading dates remain master dates
```

If the capability gate blocks panel construction, tests should instead cover the audit/parser logic and fail-closed behavior for missing availability metadata.

## 9. Candidate feature feasibility — audit only

Without training anything, classify feasibility of these future feature concepts based on actual available PIT-safe fields:

```text
revenue_ttm_growth
net_profit_ttm_growth
operating_cashflow_ttm / net_profit_ttm
ROE_TTM
liability_to_assets
gross_margin_ttm
PE_TTM
PB
free_cashflow_yield (only if derivable safely)
```

For each choose:

```text
DIRECTLY_AVAILABLE
DERIVABLE_PIT_SAFE
DERIVABLE_BUT_MISSING_REQUIRED_HISTORY
PIT_UNSAFE
UNAVAILABLE
```

Do not calculate a feature merely to make it available; correctness and lineage are the gate.

## 10. No model / no tuning

This task must not:

- fit LightGBM or any other model;
- run V3 performance backtests;
- optimize any feature;
- change y20;
- add sector/technical indicators;
- use Qlib/RL;
- change V1/V2 code;
- change execution semantics.

The purpose is to decide whether a fundamental/valuation challenger is technically legitimate before authorizing it.

## 11. Data-source restrictions

Primary audit source is the **existing local MiniQMT/XtQuant environment**.

Do not install packages.
Do not use web-scraped financial data.
Do not silently introduce AkShare/Tushare/Baostock or another provider.

If local XtQuant is insufficient, report exactly what is missing. A later Architect task can explicitly choose a second data source if needed.

## 12. Safety

No broker write actions.
No send/cancel.
No QmtGateway changes.
No MiniQMT configuration changes.
No VeighNa Studio modifications.

```text
QmtGateway write path = NOT AUTHORIZED
live trading = NONE
```

## 13. Environment health

Run `python -m pip check` as a diagnostic only.

The known warning is:

```text
peewee 3.17.3
vnpy-sqlite/mysql/postgresql require >=3.17.9
```

Do not repair dependencies in this task.

## 14. Allowed files

Prefer an isolated audit implementation:

```text
scripts/midea_fundamental_data_capability_audit.py
tests/strategies/test_midea_fundamental_data_capability.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260908.md
```

If a small pure helper is genuinely useful, this additional file is allowed:

```text
src/trader/strategies/midea_timing/fundamental_pit.py
```

Generated raw extracts / CSV / JSON / proof panels must remain under `work/` and must not be committed.

Do not modify existing locked implementation files.

## 15. Required report

Write:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260908.md
```

The report must include:

1. exact local API/import capability;
2. exact financial table/category names and raw field names;
3. point-in-time availability timestamp evidence;
4. restatement/revision evidence and classification;
5. 2014-2026 coverage table;
6. valuation/share-capitalization availability;
7. candidate-feature feasibility matrix;
8. as-of proof panel evidence if PIT-safe;
9. deterministic tests/results;
10. environment health;
11. explicit zero-live-trading side effects;
12. one final gate conclusion from:

```text
PIT_FUNDAMENTALS_READY
PIT_FUNDAMENTALS_PARTIAL
BLOCKED_FOR_PIT_FUNDAMENTALS
```

`PIT_FUNDAMENTALS_READY` requires reliable historical availability timestamps and no unresolved latest-restatement leakage for the fields proposed for the next challenger.

## Definition of Done

```text
[ ] installed XtQuant financial capability is inspected, not assumed
[ ] exact APIs/tables/fields are reported
[ ] report-period vs publication-time distinction is enforced
[ ] restatement/revision risk is explicitly classified
[ ] 2014-2026 coverage is quantified
[ ] candidate feature feasibility matrix is complete
[ ] PIT as-of proof is built only if safe
[ ] leakage tests pass or audit fails closed
[ ] no ML/backtest optimization is performed
[ ] no dependency mutation
[ ] locked V1/V2/baseline/QmtGateway unchanged
[ ] no live trading side effects
```
