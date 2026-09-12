# TASK — Fix Midea Fundamental / Valuation PIT Data Capability Audit

Date: 2026-09-12

Based on review: `interactive/REVIEW_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260912.md`

State: **AUTHORIZED**

Target: `000333.SZ`

Nature: **data-lineage/audit fix only**

## 1. Goal

Correct the accepted-review blockers in commit `b7ad981` and produce an auditable,
fail-closed answer to the existing PIT fundamentals capability question.

This task does not authorize a fundamental model, feature optimization, V3
backtest, order submission, cancellation, or gateway changes.

The starting gate remains:

```text
PIT_FUNDAMENTALS_PARTIAL
```

Do not upgrade it to `PIT_FUNDAMENTALS_READY` unless every readiness condition in
this task is evidenced. A corrected `PIT_FUNDAMENTALS_PARTIAL` result is acceptable.

## 2. Mandatory fix A — report the installed version truthfully

Record separately:

```text
importlib.metadata.version("xtquant")
xtquant.__version__ if present
xtquant import path
advertised update version, if the import-time message emits one
```

Do not call an advertised update the installed version. Do not upgrade anything.

## 3. Mandatory fix B — validate availability fields

For every availability-related field used or mentioned, report:

```text
schema presence
valid/nonzero value count
missing/zero/NaN count
first and last valid value
time precision actually observed
```

For the current data, treat midnight-only `m_anntime` values conservatively as
date-level evidence unless exact intraday precision is independently proven.
Date-level disclosures become usable on the next Midea trading session.

`actual_ann_dt` must be reported as unusable if it remains all zero. Do not use
`m_timetag`, `m_quarter`, or report period as an availability timestamp.

## 4. Mandatory fix C — field-level coverage and feature classification

Replace schema-union classification with evidence by exact table and field.
For every raw ingredient used by the candidate matrix, report:

```text
source table
non-null row count
distinct fiscal periods with a valid value
first/last valid fiscal period
records with valid availability timestamp
obvious missing periods
```

Classify the feature concept, not merely its ingredients, using exactly one of:

```text
DIRECTLY_AVAILABLE
DERIVABLE_PIT_SAFE
DERIVABLE_BUT_MISSING_REQUIRED_HISTORY
PIT_UNSAFE
UNAVAILABLE
```

Rules:

- `DIRECTLY_AVAILABLE` only if the exact finished feature is supplied directly.
- TTM, growth, margin, ROE, leverage and valuation ratios are derived unless an
  exact source field with matching semantics is proven.
- State the required deterministic formula and quarterly/cumulative-flow handling
  for every derived concept, but do not calculate or optimize features in this task.
- If revision policy or required history is unresolved, do not label the concept
  `DERIVABLE_PIT_SAFE`.
- PE/PB/free-cash-flow yield require audited point-in-time shares and an exact-date
  unadjusted-price capability/coverage check. Do not use back-adjusted price.
- Check denominator-zero/missing-value requirements explicitly.

## 5. Mandatory fix D — revision evidence and frozen proof policy

For several duplicate fiscal periods in Income, Balance, CashFlow and
PershareIndex, compare selected business-field values across each `m_anntime`.
Report separately:

```text
duplicate period, identical selected values
duplicate period, changed selected values
```

Do not infer that every later row is a correction from timestamp differences alone.

Freeze one explicit proof-panel revision policy. Recommended policy:

```text
AS_REVISED_WHEN_DISCLOSED
```

Under that policy, each version becomes eligible only from the first Midea trading
session strictly after its own date-level `m_anntime`. Earlier trading dates retain
the earlier disclosed version. For a given table/fiscal period/date, select the
latest version eligible as of that date; never overwrite historical states with a
future revision.

If the implementation chooses first-disclosure-only instead, name it explicitly,
justify it, and test it. Do not mix policies.

## 6. Mandatory fix E — persist the daily proof panel under work/

Write a machine-readable proof artifact, for example:

```text
work/midea_fundamental_asof_proof.csv
```

Use the existing Midea trading-date series as the exact master calendar. Include
all master dates in order and at least these raw concepts where available:

```text
revenue
net_profit_excl_min_int_inc
net_cash_flows_oper_act
tot_assets
tot_liab
total_capital
```

For every value, include enough lineage to identify:

```text
source table
fiscal period
source m_anntime
first eligible trading date
revision/version policy
```

Forward-carry of the last disclosed eligible record is valid as an as-of operation;
backward fill from a future disclosure is forbidden. Do not fabricate missing
quarters. Raw/generated artifacts stay in `work/` and must not be committed.

The summary JSON must contain the proof artifact path, row count, SHA-256, date
range and schema so a reviewer can verify it independently.

## 7. Mandatory fix F — paired disclosure boundaries

Emit and report 3-5 deterministic paired boundaries. Each pair must show:

```text
last Midea trading date before activation + old eligible period/value
first eligible Midea trading date          + new eligible period/value
source m_anntime
```

Include at least one Income field, one Balance field and one CashFlow field.
CapitalStructure may be additional evidence but cannot be the only source.

## 8. Mandatory fix G — quarterly/annual coverage

Report coverage by validated fiscal-period dates:

```text
Q1 ending 03-31
Q2/half-year ending 06-30
Q3 ending 09-30
year-end ending 12-31
```

State that `m_quarter` is unusable if it remains zero/invalid. Report counts and
missing expected fiscal periods without filling them. Explain the 2013Q4/2013
annual gap or retain it as an explicit readiness blocker.

## 9. Mandatory tests

Add deterministic tests for at least:

```text
[ ] report period alone never activates a record
[ ] missing/zero/NaN availability timestamp fails closed
[ ] date-only disclosure activates on the next actual master trading session
[ ] Friday disclosure does not activate Saturday/Sunday
[ ] holiday gap uses the next supplied Midea session
[ ] invalid policy value is rejected/fails closed
[ ] unsorted or duplicate master dates are rejected, or normalized explicitly and tested
[ ] disclosure-before/after boundary pair contains old and new states
[ ] future revision does not alter earlier as-of rows
[ ] selected revision changes only after its own eligible session
[ ] identical duplicate and changed duplicate are classified separately
[ ] field schema presence with all-null values is not treated as available history
[ ] feature labels follow the exact finished-feature semantics
[ ] proof-panel row count and dates equal the master calendar
[ ] no backward fill of future fundamentals
```

Report the actual number of tests; do not hard-code an incorrect count.

## 10. Failure semantics

Do not classify every exception as `BLOCKED_DATA_SERVICE_DOWN`.
Distinguish at minimum:

```text
data service unavailable
input/master-data missing
schema or field-contract failure
PIT validation failure
unexpected implementation error
```

Return a nonzero exit status for a failed audit. Do not emit a successful-looking
summary when the audit has failed.

## 11. Allowed files

The Agent may modify only:

```text
scripts/midea_fundamental_data_capability_audit.py
src/trader/strategies/midea_timing/fundamental_pit.py
tests/strategies/test_midea_fundamental_data_capability.py
```

Add exactly one new implementation report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_FIX_20260912.md
```

Do not modify the original task, original implementation report, this review, or
this fix task. Do not modify locked baseline/V1/V2/history/QmtGateway files.

Generated CSV/JSON/raw extracts remain under ignored `work/` and are not committed.

## 12. Required validation

Run and report:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest tests.strategies.test_midea_fundamental_data_capability -v
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Also verify by repository diff that locked baseline, V1/V2, history-study and
QmtGateway files are unchanged. `pip check` is diagnostic only; do not repair the
known peewee warning.

The live/cached audit rerun may use only `xtdata` read/download financial and
market-data functions. It must not import or call `XtQuantTrader`, send/cancel,
fund transfer, or any broker write API.

## 13. Required implementation report

The new report must include:

1. exact installed package/version evidence;
2. availability-field validity counts and precision;
3. exact raw-field coverage by table and fiscal period;
4. corrected candidate-feature classifications and reasons;
5. duplicate/revision value-level evidence and frozen policy;
6. proof-panel path/hash/schema/range/row count;
7. 3-5 paired before/after disclosure boundaries;
8. quarterly/year-end coverage and gaps;
9. targeted and full test results;
10. environment health and locked-file diff evidence;
11. zero broker-write side effects;
12. one final gate conclusion.

Allowed final conclusions:

```text
PIT_FUNDAMENTALS_READY
PIT_FUNDAMENTALS_PARTIAL
BLOCKED_FOR_PIT_FUNDAMENTALS
```

## 14. Definition of Done

```text
[ ] installed XtQuant version is distinguished from advertised update
[ ] availability fields have value-level validity evidence
[ ] actual_ann_dt is not claimed usable when all zero
[ ] field coverage is based on non-null values, not schema union
[ ] feature concepts use correct direct/derived/PIT classifications
[ ] revision evidence distinguishes identical vs changed values
[ ] one revision policy is frozen and tested
[ ] daily as-of proof panel is persisted under work/
[ ] proof artifact path/hash/range/schema are reported
[ ] 3-5 paired statement disclosure boundaries are reported
[ ] quarterly/year-end coverage and gaps are quantified
[ ] weekend/holiday and future-revision leakage tests pass
[ ] audit failures return nonzero and are classified accurately
[ ] targeted and full repository tests pass
[ ] no dependency mutation
[ ] locked files and QmtGateway remain unchanged
[ ] no model/backtest optimization
[ ] no live trading side effects
```

## 15. Safety boundary

```text
research/data audit only
QmtGateway write path = NOT AUTHORIZED
live trading          = NONE
dependency mutation   = NOT AUTHORIZED
D:\veighna_studio      = READ ONLY
```
