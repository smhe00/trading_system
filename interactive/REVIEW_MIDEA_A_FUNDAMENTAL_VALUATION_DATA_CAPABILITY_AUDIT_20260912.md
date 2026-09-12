# REVIEW — Midea A Fundamental / Valuation PIT Data Capability Audit

Date: 2026-09-12

Architect review of Agent commit: `b7ad98176a5eacf271aaeff48b94421fce73e738`

Task: `interactive/TASK_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260908.md`

Verdict: **CHANGES_REQUIRED**

## 1. Gate decision

The narrow capability audit is directionally useful, but it is not yet accepted.

```text
MIDEA_A_FUNDAMENTAL_VALUATION_PIT_AUDIT = CHANGES_REQUIRED
CURRENT_GATE                                = PIT_FUNDAMENTALS_PARTIAL
FUNDAMENTAL_CHALLENGER_V3                   = NOT AUTHORIZED
```

The local source does expose populated `m_anntime` values and multiple historical
rows for some fiscal periods. However, the committed evidence overstates the
installed version and feature readiness, and it does not deliver the required
daily as-of proof panel or paired disclosure-boundary evidence.

## 2. What passed review

The Agent changed exactly the four authorized files between task commit `6b1ee29`
and implementation commit `b7ad981`:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260908.md
scripts/midea_fundamental_data_capability_audit.py
src/trader/strategies/midea_timing/fundamental_pit.py
tests/strategies/test_midea_fundamental_data_capability.py
```

No locked MA/V1/V2 implementation, QmtGateway, dependency declaration, MiniQMT
configuration, or VeighNa Studio file was changed. Static inspection found no
broker order/cancel path in the new audit code.

Independent verification on 2026-09-12:

```text
new audit tests: 12/12 PASS
full repository tests: 158/158 PASS
git diff --check: PASS
```

The local MiniQMT/xtdata service was reachable read-only at `127.0.0.1:58610`.
Using the cached `report_time` data for `000333.SZ`, 2014-01-01..2026-09-04,
the reviewed five tables returned the same row counts reported by the Agent.
The required raw ingredients inspected during review were non-null across 50
distinct fiscal periods for the three statements, and share-capital fields were
non-null across 216 capital-structure records.

The existing environment-health warning is reproduced and remains diagnostic:

```text
peewee 3.17.3
vnpy-sqlite/mysql/postgresql require >=3.17.9
```

No dependency repair is authorized by this review.

## 3. Blocking findings

### 3.1 Installed XtQuant version is reported incorrectly

The implementation report says the installed package is `xtquant 250807.1.2`.
Independent inspection shows:

```text
importlib.metadata.version("xtquant") = 250516.1.1
xtquant.__version__                   = xtquant_250516
```

`250807.1.2` is the update advertised by the package's import-time message, not
the installed version. The task explicitly requires exact local package metadata.

### 3.2 Candidate-feature readiness is overclassified

The audit marks six feature concepts `DIRECTLY_AVAILABLE` whenever their raw
ingredient field names exist in the union of table schemas. That is not the task's
classification contract.

For example:

```text
revenue_ttm_growth
net_profit_ttm_growth
operating_cashflow_ttm / net_profit_ttm
ROE_TTM
liability_to_assets
gross_margin_ttm
```

are calculated features, not direct raw fields. They require PIT-safe quarterly
selection, cumulative-flow handling, TTM construction, growth/ratio formulas,
denominator rules, and a frozen restatement policy. Schema membership also does
not prove that a field is populated for the required history.

The fix must audit non-null field coverage by table and fiscal period, distinguish
raw ingredients from finished features, and use only the five allowed task labels.
`DIRECTLY_AVAILABLE` is valid only when the exact feature itself is directly
supplied with PIT-safe history.

### 3.3 Required daily as-of proof artifact is missing

`build_as_of_panel()` creates an in-memory list, but the committed audit output
retains only counts and a few `example_boundaries`. No daily as-of mapping is
written under `work/`.

The task required a minimal daily proof panel on Midea trading dates, with 3-5
raw fields, and no future record visible before its eligible session. A count of
active records is not an auditable replacement for that artifact.

### 3.4 Disclosure-boundary proof is incomplete

The report shows only three single-row examples, primarily capital-structure
events. It does not provide the required paired evidence:

```text
trading day before disclosure boundary -> old eligible record/value
first eligible trading day after boundary -> new eligible record/value
```

The fix must provide 3-5 paired boundaries, including statement fields rather
than only capital-structure events.

### 3.5 `actual_ann_dt` is not usable evidence in this extraction

The report labels `actual_ann_dt` as an observed supplemental announcement date.
In the reviewed `ASHAREINCOME` extract, all 77 rows contained numeric zero for
that field. It is present in the schema but has no populated evidence value and
must not support the PIT gate.

### 3.6 Revision evidence needs value-level qualification

Different `m_anntime` values for the same `m_timetag` prove that multiple dated
rows exist. They do not alone prove that every duplicate is a correction.
Independent examples show both patterns:

```text
same period + later m_anntime + identical selected values
same period + later m_anntime + changed selected values
```

The fix must compare selected field values across versions, report identical and
changed duplicates separately, and freeze an explicit as-of revision policy for
the proof panel. It must not silently treat a later value as if it were known at
the first disclosure.

### 3.7 Test/report claims are inaccurate or incomplete

The report claims 13 new deterministic tests; the file contains and runs 12.
Also, the test constant named `WEEKDAYS` is ten consecutive calendar dates and
contains Saturday/Sunday. It cannot prove that a Friday/date-only disclosure
activates on the next actual trading session rather than the next calendar day.

The fix needs explicit exchange-session fixtures covering weekend and holiday
gaps, plus a test that invalid policy values fail closed rather than implicitly
falling into same-day behavior.

### 3.8 Quarterly/annual coverage is not actually classified

The task asks for quarterly versus annual coverage. In the reviewed raw data,
`m_quarter` is `0` throughout the statement tables, so it is not usable as a
quarter classifier. The fix must state that limitation and classify cadence from
validated fiscal-period dates, with counts for Q1/Q2/Q3/year-end periods and
explicit gaps. It must not describe `m_quarter` as meaningful evidence.

## 4. Required disposition

Keep the gate at:

```text
PIT_FUNDAMENTALS_PARTIAL
```

Do not build, train, tune, or backtest a fundamental challenger until the follow-up
fix task passes review. The follow-up may improve the audit and proof artifacts;
it does not authorize model work or any broker write path.

## 5. Safety boundary

```text
research/data audit only
QmtGateway write path = NOT AUTHORIZED
live trading          = NONE
dependency mutation   = NOT AUTHORIZED
D:\veighna_studio      = READ ONLY
```
