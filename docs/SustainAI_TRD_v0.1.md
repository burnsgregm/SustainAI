SustainAI: Technical Requirements Document (TRD)
Project: SustainAI, Predictive Sustainment and Supply-Exception Triage (working name)
Author: Gregory Burns Version: 0.1 (Draft) Date: July 6, 2026 Status: In development.
Builds on BRD v0.1 and SDD v0.1 (both approved). This document is written to be
executable by a coding agent as well as a human engineer. Where a value is provisional it is
marked PROVISIONAL; where a value must be determined empirically during the build it
is marked TBD-EMPIRICAL with the procedure for determining it. No performance results
exist yet. Nothing in this document is a claimed result.
0. Instructions to the Build Agent (read first, binding)
These constraints override any inference the build agent makes from context, training data,
or "best practice":
1. Scope is a contract. Build exactly what this TRD specifies. Do not add datasets,
dashboards, additional agents, streaming infrastructure, orchestrators (no Airflow, no
Prefect, no Dagster), retraining pipelines, or any component not listed here. If a
requirement seems to demand something out of scope, stop and flag it rather than
building it.
2. Never fabricate metrics. All performance numbers must come from executing the
evaluation harness (Section 10). Until the harness runs, every results field in code,
docs, and reports reads exactly: . Do not insert
TBD, pending evaluation harness
plausible-looking placeholder numbers anywhere, including in README files,
docstrings, or example outputs.
3. Leakage rules are absolute. All fitting (normalization statistics, sensor drop list,
threshold tuning, model selection) uses training-split data only, per Section 5.4. The
test set is touched exactly once, by the final harness run per model.
4. Fail-safe rules are absolute. The guardrails in Section 8.6 are not optional behaviors;
they are requirements with tests.
5. No secrets in the repo. Credentials via environment variables locally and Secret
Manager on GCP. If a credential appears in code or config, that is a defect.
6. Determinism. All random operations take seeds from config (default 42). Two runs
on identical inputs and config must produce identical predictions, exceptions, and
metric values (agent text may vary; agent decisions are constrained by Section 8).
7. When this TRD conflicts with the SDD or BRD, this TRD wins, and the conflict
should be flagged for human review.
1. System Summary (normative)
SustainAI ingests NASA C-MAPSS subset FD001, trains a model to predict remaining
useful life (RUL) per engine, thresholds predicted RUL into severity bands, emits exception
objects for Critical and Warning engines, triages each exception with a single LLM-backed
agent (Gemini on Vertex AI) that has three read-only context tools, produces validated
triage records and rendered reports, exposes the pipeline through a FastAPI service, and
measures the entire chain with an evaluation harness. Execution is batch-canonical, local-
first, with a scripted transient Cloud Run deployment.
2. Repository Structure (required layout)
sustainai/
README.md # status, setup, run commands; results section
reads TBD until harness runs
pyproject.toml # deps pinned; Python >= 3.11
Makefile # targets: setup, ingest, features, train, run,
triage, evaluate, test, serve, docker-build
.env.example # every env var in Section 3, with safe
defaults, no real credentials
docker/Dockerfile
deploy/terraform/ # minimal Cloud Run + GCS + service account;
apply and destroy documented
configs/
default.yaml # all tunables in Section 3.2
data/
raw/ # FD001 files land here (gitignored)
canonical/ # Parquet (gitignored)
features/ # feature matrices (gitignored)
models/ # serialized models + metadata (gitignored
except metadata JSON)
outputs/
runs/<run_id>/ # exceptions, triage records, reports, queue
summary
eval/<eval_id>/ # harness outputs (metrics JSON + per-engine
itemization)
src/sustainai/
ingest.py
features.py
train.py # baseline + champion training, selection logic
predict.py
exceptions.py # exception generator
agent/
triage_agent.py
tools.py # the three read-only tools
prompts.py
stub.py # deterministic offline agent stub (Section 8.8)
guardrails.py
reports.py
api.py # FastAPI app
harness/
evaluate.py
metrics.py
schemas.py # every Pydantic model in Section 6
config.py
tests/ # pytest; requirements in Section 12
3. Configuration
3.1 Environment variables
Variable Default Purpose
GCP_PROJECT none (required for live agent) Vertex AI project
VERTEX_LOCATION us-central1 Vertex AI region
GEMINI_MODEL gemini-2.5-flash PROVISIONAL: pin to the current Agent model
stable Flash-tier model at build time
AGENT_MODE live live or stub
(Section 8.8)
SUSTAINAI_SEED 42 Global seed
3.2 Config file ( ), all tunables with defaults
configs/default.yaml
yaml
data:
rul_cap: 125 # PROVISIONAL; standard C-MAPSS practice; may
sensor_drop_variance_threshold: 1.0e-6 # relative variance below this => dr
split:
val_fraction: 0.2 # by UNIT, never by row
seed: 42
severity: # thresholds on PREDICTED RUL, in cycles
critical_max: 25 # PROVISIONAL; tuned once on validation per S
warning_max: 60 # PROVISIONAL
watch_max: 100 # PROVISIONAL
agent:
timeout_seconds: 30
max_output_tokens: 1024
temperature: 0.2
max_retries_on_malformed: 1
max_tool_calls_per_exception: 6
harness:
latency_percentiles: [50, 95]
 
4. Dataset Specification: C-MAPSS FD001
4.1 Source files (inputs, exactly three)
: 100 engine units, each run to failure.
train_FD001.txt
: 100 engine units, each truncated before failure.
test_FD001.txt
: one integer per test unit: true RUL at that unit's last observed cycle, in
RUL_FD001.txt
unit order.
4.2 Raw schema (both train and test files)
Space-delimited text, 26 columns per row, possible trailing whitespace per line:
Position Name Type
1 unit_id int
2 cycle int (monotonically increasing per unit, step 1)
3–5 op_setting_1..3 float
6–26 sensor_01..21 float
4.3 Ingestion requirements
FR-ING-1: Parse both files into the canonical schema (Section 6.1). Reject on wrong
column count, non-numeric values, or non-monotonic cycles per unit; report the
offending unit and line.
FR-ING-2: Compute training labels: for each train row,
rul = min(max_cycle(unit) -
.
cycle, rul_cap)
FR-ING-3: Attach true RUL to each test unit's final cycle from , by unit
RUL_FD001.txt
order.
FR-ING-4: Write canonical Parquet to with the schema in 6.1.
data/canonical/
Ingestion is idempotent: re-running on the same inputs overwrites identically.
4.4 Expected data characteristics (verify, do not assume)
Literature consistently reports that in FD001 the three op settings and roughly seven
sensors (commonly 1, 5, 6, 10, 16, 18, 19) are constant or near-constant. FR-ING-5: the drop
list is computed empirically from the training split using ,
sensor_drop_variance_threshold
logged, and persisted with the feature version. The literature list is an expectation to sanity-
check against, not a hardcoded truth. Marked TBD-EMPIRICAL until computed.
5. Feature Engineering Requirements
FR-FE-1: Drop the empirically determined dead channels (4.4).
FR-FE-2: For each remaining sensor, compute per-unit rolling features over a trailing
window of W cycles (default W = 20, PROVISIONAL): rolling mean, rolling standard
deviation, and delta (current value minus value W cycles prior, clipped at unit start).
Plus the raw current value and current .
cycle
FR-FE-3: Normalize all features with min-max scaling fit on the training split only;
persist the scaler with a feature version hash.
FR-FE-4 (leakage): The validation split and the test set are transformed with frozen
parameters only. No statistic of any kind is fit on them.
FR-FE-5: Prediction-time feature computation must be byte-identical to training-time
computation: one shared code path, no reimplementation.
5.4 Splits
FR-SPL-1: Split the 100 training units into train/validation 80/20 by unit using
. Row-level splits are forbidden (leakage).
split.seed
FR-SPL-2: The 100 test units are used exactly once per final model, by the harness.
6. Data Schemas (normative, implement as Pydantic models in )
schemas.py
6.1 Canonical record (Parquet)
unit_id:int, cycle:int, op_setting_1..3:float, sensor_01..21:float, rul:int|null
(train only), true_rul_final:int|null (test final cycle only),
split:enum{train,val,test}
6.2 Prediction record
unit_id:int, cycle:int (latest observed), predicted_rul:float, model_id:str,
feature_version:str, run_id:str, created_at:iso8601
6.3 Exception object
exception_id: str (uuid4)
run_id: str
unit_id: int
predicted_rul: float
severity_band: enum {critical, warning} # watch/normal never generate
exceptions
thresholds_used: {critical_max:int, warning_max:int, watch_max:int}
model_id: str
created_at: iso8601
6.4 Triage record (the agent's output contract; validation is mandatory)
triage_id: str (uuid4)
exception_id: str
engine: {unit_id:int, predicted_rul:float, severity_band:str}
severity_assessment:
agrees_with_band: bool
assessed_band: enum {critical, warning, watch, normal}
reasoning: str (1..1200 chars)
context:
sensor_trend_summary: str (1..1200 chars)
degradation_summary: str (1..1200 chars)
fleet_position: str (1..600 chars)
tool_calls_made: int
recommended_action:
action_type: enum {prioritize_maintenance, schedule_inspection,
continue_monitoring}
horizon_cycles: int >= 0
details: str (1..1200 chars)
escalation:
escalate: bool
forced_by_guardrail: bool # true when Section 8.6 rules forced the
value
rationale: str (1..1200 chars)
meta:
agent_mode: enum {live, stub}
agent_model: str
latency_ms: int
failure_mode: enum {none, timeout, malformed_output, tool_error}
schema_version: str
created_at: iso8601
A record that fails validation after the permitted retry is replaced by a fail-safe record:
set accordingly, , ,
failure_mode escalation.escalate = true forced_by_guardrail = true
all free-text fields set to the literal string .
triage unavailable
6.5 Queue summary (per run)
run_id, created_at, engines_processed:int, counts_by_band:
{critical,warning,watch,normal}, exceptions_total:int, escalated:int,
logged_only:int, guardrail_forced:int, agent_failures:int, escalation_list:[{unit_id,
predicted_rul, severity_band, action_type, triage_id}], all_records_index:[triage_id]
7. Prediction and Exception Requirements
7.1 Models
FR-MOD-1 (baseline): gradient boosting regression (XGBoost or scikit-learn
; pick one, document why) on the Section 5 features,
HistGradientBoostingRegressor
tuned lightly on the validation split.
FR-MOD-2 (champion candidate): a regularized feed-forward neural network
(Keras), depth/width tuned on validation. Dropout and L2 permitted; anything
beyond a plain MLP is out of scope.
FR-MOD-3 (selection rule): the champion ships only if it beats the baseline on
validation critical-class recall at equal-or-better precision, and no worse NASA score
(Section 10.2). Otherwise the baseline ships and the README says so. The selection
decision and numbers are recorded in .
models/selection_report.json
FR-MOD-4: the shipped model is serialized with metadata: , training config
model_id
hash, feature version, seed, training timestamp.
7.2 Prediction
FR-PRD-1: For each engine in the target split, predict RUL at its latest observed cycle.
Output Section 6.2 records.
FR-PRD-2: Predicted RUL is clipped to .
[0, rul_cap]
7.3 Severity thresholding and exception generation
FR-EXC-1: Map predicted RUL to bands: if ;
critical predicted_rul <= critical_max
if ; if
warning critical_max < predicted_rul <= warning_max watch warning_max <
; else .
predicted_rul <= watch_max normal
FR-EXC-2: Emit one exception object per critical or warning engine. Watch and
normal are recorded in the run output but generate no exception.
FR-EXC-3 (threshold fixing procedure, binding): starts at the
critical_max
provisional 25 and may be tuned once, on the validation split only, by minimizing a
cost function with cost(false negative) : cost(false positive) = 10 : 1 (PROVISIONAL
ratio, revisable once under Section 11.3 with written rationale). The tuned value is
frozen in config before the harness ever touches the test set, and the tuning is
recorded in . and are operator-
models/threshold_report.json warning_max watch_max
policy values, not tuned against labels.
8. Triage Agent Requirements
8.1 Invocation
FR-AGT-1: One agent invocation per exception object. Input: the exception object plus
nothing else. All additional context comes through tools.
8.2 Tools (read-only; exact signatures)
python
get_sensor_trends(unit_id: int, last_n_cycles: int = 50) -> SensorTrends
# returns, for each informative sensor: recent values (downsampled to <= 25 poi
# direction (increasing/decreasing/stable), and rate vs the unit's own baseline
get_degradation_history(unit_id: int) -> DegradationHistory
# returns the predicted-RUL trajectory for this unit across its observed cycles
# (computed by the shipped model), plus cycles observed and current predicted R
get_fleet_summary() -> FleetSummary
# returns counts by severity band for the current run and this unit's predicted
# percentile within the fleet
 
FR-AGT-2: Tools read from the current run's artifacts only. They cannot write, cannot
reach the network, cannot see true RUL or any label. A tool exposing label data to the
agent is a critical defect (it would contaminate any judgment-quality analysis).
FR-AGT-3: Tool calls per exception capped at .
max_tool_calls_per_exception
8.3 Required agent behavior (prompt contract)
The system prompt (in , versioned) must instruct the agent to, in order: (1)
prompts.py
assess whether the severity band fits the evidence, stating agreement or dissent with
reasons; (2) gather context via tools; (3) draft one recommended action from the closed
enum with a concrete ; (4) decide escalate or log, with
action_type horizon_cycles
rationale addressed to a maintenance planner; (5) output only JSON conforming to Section
6.4. Plain, direct language; no marketing tone.
8.4 Output handling
FR-AGT-4: Parse and validate against the 6.4 schema. On malformed output, retry
once with the validation error appended. On second failure, emit the fail-safe record.
8.5 Bounds
FR-AGT-5: , , from config. Timeout
timeout_seconds max_output_tokens temperature
triggers the fail-safe record with .
failure_mode = timeout
8.6 Guardrails (deterministic, enforced in , after agent output)
guardrails.py
FR-GRD-1: If and the agent sets , the
severity_band == critical escalate = false
record is overridden to , , and the
escalate = true forced_by_guardrail = true
agent's dissenting rationale is preserved verbatim in .
escalation.rationale
FR-GRD-2: Any forces .
failure_mode != none escalate = true
FR-GRD-3: Guardrail actions are counted in the queue summary ( ).
guardrail_forced
Silent overrides are forbidden.
8.7 Determinism boundary
Agent free-text may vary between runs. Agent decisions ( , ,
escalate action_type
) are made reproducible in tests via the stub (8.8); live-mode decision
assessed_band
variance is acceptable in production runs and is bounded by guardrails.
8.8 Offline stub (required)
FR-STB-1: replaces the LLM with a deterministic rule-based stub
AGENT_MODE=stub
that produces schema-valid records (e.g., escalate iff band is critical or predicted RUL
within 5 cycles of ). Purpose: tests and CI run with zero credentials and
critical_max
zero cost. The stub must exercise the same validation, guardrail, and fail-safe code
paths as live mode.
9. API Requirements (FastAPI)
Method Path Behavior
POST /runs Trigger a full pipeline run on the configured
split; returns {run_id} (202)
GET /runs/{run_id} Run status plus queue summary (6.5) when
complete
GET /runs/{run_id}/exceptions List exception objects
GET /exceptions/{exception_id} Exception plus its triage record
POST /exceptions/{exception_id}/triage Re-triage on demand; returns the new
record
GET /health {status, model_id, agent_mode,
schema_version}
FR-API-1: All request/response bodies are the Pydantic models of Section 6. Errors
return structured JSON with a machine-readable code.
FR-API-2: The API never fabricates or caches stale metrics; it serves artifacts from
.
outputs/
10. Evaluation Harness (the only source of performance claims)
10.1 Execution
FR-EVA-1: The harness runs the full chain (predict, threshold, exception, triage,
report) on the 100 test units, using the frozen model, frozen features, and frozen
thresholds. One command: . Output to :
make evaluate outputs/eval/<eval_id>/
, , , , ,
metrics.json per_engine.json misses.json false_alarms.json latency.json
plus the config snapshot that produced them.
FR-EVA-2: Ground truth: a test engine is truly critical iff
true_rul_final <=
(the same frozen threshold applied to true RUL). Predicted critical iff
critical_max
.
predicted_rul <= critical_max
10.2 Metrics (exact definitions)
Regression quality (on all 100 test units):
RMSE and MAE of predicted vs true RUL at last observed cycle.
NASA C-MAPSS scoring function: with per unit, score
d = predicted_rul - true_rul
for and for . Lower is
s = Σ [exp(-d/13) - 1] d < 0 Σ [exp(d/10) - 1] d >= 0
better; late predictions are penalized more than early ones, which matches the
operational asymmetry.
Critical-class classification (the headline metrics):
Precision = TP / (TP + FP), Recall = TP / (TP + FN), F1, and the full confusion matrix,
where positive = critical per FR-EVA-2.
FR-EVA-3 (itemization): lists every false negative by with
misses.json unit_id
predicted and true RUL; likewise for false positives. Aggregate
false_alarms.json
numbers without the itemized lists do not satisfy this requirement.
Band accuracy: fraction of test units whose predicted band equals their true band (true
band computed from with the same thresholds).
true_rul_final
Triage responsiveness: per-exception latency ( , measured from agent
meta.latency_ms
invocation to validated record), reported at p50 and p95, plus end-to-end pipeline wall-
clock. Live-mode latency is the number that counts; stub latency is reported separately and
never substituted.
Triage integrity: percent of triage records schema-valid on first attempt; count of retries,
failures, guardrail overrides; escalation selectivity = escalated / exceptions.
10.3 Provisional targets (commitments to measure against, not results)
Metric Target Status
Critical-class recall >= 0.80 PROVISIONAL
Critical-class precision >= 0.65 PROVISIONAL
NASA score beat the baseline model's score fixed rule
Triage latency p95 (live) <= 15,000 ms per exception PROVISIONAL
Schema-valid on first attempt >= 0.95 PROVISIONAL
Pipeline wall-clock (local, stub) <= 10 minutes PROVISIONAL
Each PROVISIONAL target may be revised exactly once, before final evaluation, with
rationale recorded per Section 11.3.
11. Non-Functional Requirements
NFR-1 (reproducibility):
make setup && make ingest && make features && make train
from a clean clone with FD001 files in
&& make run && make evaluate data/raw/
reproduces the pipeline deterministically (stub mode) with no manual steps.
NFR-2 (cost): Zero standing cloud cost. Live agent cost bounded by token caps; a full
100-unit run's Vertex spend is logged and reported.
NFR-3 (revision log, binding): records every revision of a
docs/decisions.md
PROVISIONAL value: old value, new value, evidence, date. The one-revision rule from
the BRD is enforced editorially through this file.
NFR-4 (security): no credentials in repo; service account with least privilege (Vertex
invoke, GCS read/write to one bucket) in the Terraform.
NFR-5 (code quality): type hints throughout; ruff clean; every module in Section 2
has a docstring stating its boundary per the SDD.
NFR-6 (honesty in artifacts): README and reports must not contain performance
numbers unless copied from a produced by FR-EVA-1, with the
metrics.json
cited.
eval_id
12. Testing Requirements (pytest, all runnable in stub mode with no
credentials)
T-1: ingestion rejects malformed input (wrong columns, non-monotonic cycles) with
actionable errors.
T-2: RUL labeling correct at boundaries (cap applied; final cycle rul = 0 for train units).
T-3: unit-level split contains no unit in two splits; frozen transforms never refit on
val/test (assert scaler parameters unchanged).
T-4: thresholding maps band boundaries exactly per FR-EXC-1 (test values at, just
below, just above each threshold).
T-5: exception generation emits exceptions only for critical and warning.
T-6: triage record validation rejects each required-field omission and each enum
violation.
T-7: guardrail FR-GRD-1: stub configured to say on a critical; assert
escalate=false
override, flag, and preserved rationale.
T-8: fail-safe: forced timeout and forced malformed output both yield valid fail-safe
records with .
escalate=true
T-9: tools cannot access label fields (assert label columns absent from tool-visible
data).
T-10: harness metric math verified against hand-computed values on a fixture of 10
synthetic units (including the NASA score, both branches).
T-11: API contract tests for every endpoint in Section 9 (stub mode).
T-12: determinism: two full stub-mode runs produce identical predictions, exceptions,
and metrics.
13. Acceptance Criteria (definition of done)
The build is done when all of the following are true:
1. AC-1: NFR-1 reproducibility command sequence succeeds from a clean clone.
2. AC-2: All tests in Section 12 pass in stub mode with no credentials.
3. AC-3: The harness has produced on the test set for the shipped model,
metrics.json
including itemized and (FR-EVA-3).
misses.json false_alarms.json
4. AC-4: A full live-mode run (real Gemini) has completed on all test-set exceptions,
with latency measured and Vertex cost logged.
5. AC-5: Model selection report and threshold report exist and justify the shipped
configuration (FR-MOD-3, FR-EXC-3).
6. AC-6: Guardrail and fail-safe behavior demonstrated in the live run's queue summary
counters (or explicitly reported as zero occurrences).
7. AC-7: exists and every PROVISIONAL revision (if any) is logged
docs/decisions.md
with rationale; no value revised more than once.
8. AC-8: README results section contains only harness-produced numbers with
citations, or the literal text .
eval_id TBD, pending evaluation harness
9. AC-9: Terraform apply/destroy cycle for the demo deployment verified once and
documented; standing cost after destroy is zero.
10. AC-10: Nothing outside the Section 6.2 in-scope list of the BRD exists in the repo.
14. Open Items (tracked, not blockers to starting)
1. Exact pin (check current stable Flash-tier model at build start).
GEMINI_MODEL
2. Empirical sensor drop list and confirmation of the literature expectation (FR-ING-5).
3. Rolling window W final value (validation evidence, one revision permitted).
4. Final tuned (FR-EXC-3 procedure).
critical_max
5. Whether XGBoost or HistGradientBoostingRegressor serves as baseline (pick at build
start, document in selection report).