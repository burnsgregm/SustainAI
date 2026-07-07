# SustainAI

Predictive sustainment and supply-exception triage on NASA C-MAPSS FD001. One dataset, one pipeline, one agent, one evaluation harness. An RUL model predicts engine degradation, deterministic thresholds convert predictions into severity-banded exceptions, and a single LLM-backed agent triages each exception behind hard guardrails: a Critical can never be silently suppressed, and any agent failure fails safe to escalation.

Design documents: [BRD](docs/SustainAI_BRD_v0.1.md) | [SDD](docs/SustainAI_SDD_v0.1.md) | [TRD](docs/SustainAI_TRD_v0.1.md)
Audit trail: [decisions.md](docs/decisions.md) | [deviations.md](docs/deviations.md)

## Results (Eval ID: eval-24243a5a)

Measured by the evaluation harness on the 100-engine FD001 test set. This eval reproduces eval-8a40e13a exactly (bit-identical prediction metrics across independent runs).

| Metric | Value |
|---|---|
| Critical-class recall | 0.842 (target 0.80: PASS) |
| Critical-class precision | 0.941 (target 0.65: PASS) |
| Critical-class F1 | 0.889 |
| Critical confusion | 16 caught, 3 missed, 1 false alarm, of 19 truly critical |
| RUL RMSE / MAE (cycles) | 17.6 / 13.3 |
| NASA scoring function | 763 |
| Severity band accuracy | 0.7 |
| Agent triage | 33 exceptions, 0.0 failure rate, 100% schema validity |
| Agent latency | stub-mode p95 9 ms; live measurement pending AC-4 |

The three missed engines and the one false alarm are itemized in [misses.json](outputs_evidence/misses.json) and [false_alarms.json](outputs_evidence/false_alarms.json). An honest miss list is a feature of this project, not an admission.

## Reproduce it

```
py -3.10 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e .[dev]
# place train_FD001.txt, test_FD001.txt, RUL_FD001.txt in data/raw/
.\build.ps1 all        # or: make ingest features train run evaluate test
```

Deterministic in stub mode: identical predictions, exceptions, and metrics on every run (test T-12 enforces it).

## Scope, on purpose

FD002-FD004, dashboards, multi-agent designs, streaming, and orchestrators are explicitly out of scope (BRD 6.2). A tightly scoped system that ships and measures itself honestly was the point.
