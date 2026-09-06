# Trading System Collaboration Convention

This repository uses GitHub `main` as the shared coordination surface between Architect and implementation Agents.

## Architect -> Agent

All new task instructions, reviews, fix requests, and gate decisions are written as **new files** under:

```text
interactive/
```

Do not overwrite an earlier task file when issuing a follow-up task. Use a new descriptive filename, preferably including the task purpose and date/version.

Examples:

```text
interactive/TASK_QMT_GATEWAY_READONLY.md
interactive/REVIEW_QMT_GATEWAY_READONLY_20260906.md
interactive/TASK_QMT_GATEWAY_READONLY_HARDENING_20260906.md
```

## Agent -> Architect

Implementation Agents write their completion reports under:

```text
interactive/reports/
```

A follow-up task must use a new report filename and must not overwrite an earlier report.

Example:

```text
interactive/reports/IMPLEMENTATION_REPORT_QMT_GATEWAY_READONLY_HARDENING_20260906.md
```

## Review rule

Agent reports are not sufficient for PASS by themselves. The Architect should independently inspect the actual code and tests before issuing a gate decision.

## Safety rule

Tasks that touch broker integration must state their allowed side effects explicitly. Read-only tasks must not place or cancel real orders. Writable QMT tests require explicit task authorization and should use a simulation account unless the user explicitly authorizes otherwise.

This file is the repository-local authoritative reminder of the collaboration convention.
