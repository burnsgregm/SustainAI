SustainAI: System Design Document (SDD)
Project: SustainAI, Predictive Sustainment and Supply-Exception Triage (working name)
Author: Gregory Burns Version: 0.1 (Draft) Date: July 6, 2026 Status: In development. This
document describes how the system will be built. It builds on BRD v0.1 (approved). No
results are claimed. All performance behavior described here is design intent pending the
evaluation harness defined in the TRD.
1. Design Philosophy
Three principles govern every choice below.
1. The model does the math; the agent does the reasoning and communication. RUL
prediction is a numerical problem and stays in a trained model. Triage is a judgment-
and-explanation problem and goes to the agent. The agent never predicts and the
model never explains. Blurring this boundary is the most common failure mode in
agentic ML systems and it is designed out here.
2. The agent can filter attention but can never suppress information. Every exception,
triaged or not, escalated or not, remains in the record. Deterministic guardrails bound
what the agent can decide. An agent failure fails safe: the exception escalates
automatically.
3. Reuse proven patterns; introduce nothing new without cause. Cost-asymmetric
thresholding comes from ReneWind. Structured pipeline discipline and Terraform
deployment come from FraudShield. Durable Parquet as source of truth comes from
DemoRAG's dual-write lesson. The only genuinely new element is the triage agent,
which is exactly where the project's differentiation lives.
2. Architecture Overview
2.1 Described architecture diagram
The system is a linear pipeline with one branch. Read left to right:
[C-MAPSS FD001 files]
|
v
(1) INGESTION ................ validate schema, compute RUL labels,
| write canonical Parquet
v
(2) FEATURE ENGINEERING ...... drop dead sensors, rolling-window
| features, normalization
v
(3) PREDICTION SERVICE ....... trained RUL model, per-engine
| predictions on latest cycle
v
(4) EXCEPTION GENERATOR ...... threshold RUL into severity bands,
| emit exception objects
v
(5) TRIAGE AGENT ............. one agent, one job: assess, gather
| ^ context, recommend, escalate or log
| |
| +---- context tools (read-only): sensor trends,
| degradation history, fleet summary
v
(6) TRIAGE REPORT ............ structured JSON + rendered report
| per exception; queue summary
v
[Operator] <---- FastAPI serves all of the above;
(7) EVALUATION HARNESS runs the whole chain
on held-out engines and measures it
Components 1 through 4 are deterministic Python. Component 5 is the single LLM-backed
element. Component 7 sits outside the pipeline and exercises it end to end.
2.2 Execution model
Batch, by design. C-MAPSS is a batch dataset and the BRD scopes out streaming. A pipeline
run processes the fleet, produces the current exception queue, triages it, and emits reports.
The FastAPI layer exposes the same capabilities per-request (predict one engine, triage one
exception) so the system also demonstrates service behavior, but the canonical execution is
the batch run, because that is what the harness measures.
3. Components and Boundaries
3.1 Ingestion
Input: FD001 train/test text files as published by NASA (space-delimited: unit id,
cycle, 3 operational settings, 21 sensor channels), plus the true-RUL file for test units.
Responsibilities: schema validation (column count, types, monotonic cycles per
unit), RUL label computation for training data (linear decrease to failure, capped at a
ceiling of approximately 125 cycles per standard C-MAPSS practice, exact value fixed
in the TRD), and a canonical Parquet write.
Boundary: ingestion knows nothing about models or features. Its output contract is
the Parquet schema defined in the TRD.
Rationale for the RUL cap: early-life engines show no degradation signal; an
uncapped linear label asks the model to predict the unpredictable and corrupts
training. The cap is standard practice and will be documented as a tradeoff, not
hidden.
3.2 Feature Engineering
Responsibilities: drop constant and near-constant sensor channels (FD001 has
several; the exact drop list is decided from training-data variance and recorded),
compute rolling-window statistics (means, standard deviations, deltas) over recent
cycles per unit, and normalize using statistics fit on training data only.
Boundary: consumes canonical Parquet, emits a feature matrix. Feature definitions
are versioned in code so the harness and the service compute identical features.
Leakage discipline: all fitting (normalization statistics, sensor drop list) happens on
training units only. Test units are transformed with frozen parameters. This is stated
here because leakage is the most common way predictive-maintenance results are
silently inflated.
3.3 Prediction Service
Model strategy: baseline first, champion second, same discipline as ReneWind.
Baseline: gradient boosting regression on the engineered features. Champion
candidate: a regularized neural network. The champion must beat the baseline on the
harness metrics to earn its place; if it does not, the baseline ships and the document
says so.
Output: predicted RUL for each engine at its latest observed cycle.
Boundary: the model emits numbers only. No severity, no language, no
recommendations. Severity is policy, and policy lives in the next component where it
can be changed without retraining.
3.4 Exception Generator
Responsibilities: map predicted RUL to severity bands via fixed thresholds: Critical,
Warning, Watch, Normal (threshold values set in the TRD and tuned once against the
cost-asymmetric logic proven in ReneWind: a missed failure costs far more than a
false alarm, so thresholds lean conservative).
Emits: an exception object for every Critical and Warning engine. Watch and Normal
are recorded but generate no exception.
Boundary: deterministic, auditable, trivially testable. Separating thresholding from
prediction means the escalation policy can be tuned or reviewed without touching the
model, which is exactly how an operator organization would want it.
3.5 Triage Agent
The differentiating component and the only LLM in the system.
Model: Gemini via Vertex AI (GCP-native, per the locked stack decision).
Input: one exception object (engine id, predicted RUL, severity band, model
confidence context).
Tools (read-only, pipeline-internal):
1. : recent-cycle trajectories for the informative
get_sensor_trends(engine_id)
sensors
2. : predicted-RUL trajectory over the
get_degradation_history(engine_id)
engine's observed life
3. : where this engine sits relative to the fleet (is it an outlier
get_fleet_summary()
or one of many)
Job, in order: assess severity (agree or flag disagreement with the band, with reasons),
gather context via tools, draft a recommended action (for example: schedule
inspection within N cycles, prioritize for teardown, continue monitoring with
justification), and decide escalate versus log.
Output: a structured JSON triage record validated against a fixed schema (defined in
the TRD): severity assessment, context summary, recommended action, escalation
decision, and reasoning. Free text lives inside schema fields; the record itself is
machine-checkable.
Deterministic guardrails (policy the agent cannot override):
1. A Critical exception can never be silently downgraded to log-only. The agent
may argue for de-escalation in its reasoning, but a Critical always reaches the
operator's escalation list, flagged with the agent's dissent if there is one.
2. Any agent failure (timeout, malformed output, tool error) fails safe: the
exception auto-escalates with a "triage unavailable" marker. The agent adds
judgment; its absence never subtracts safety.
3. Token and context budgets are capped per exception so cost and latency stay
bounded and measurable.
What the agent is not: it does not retrain anything, does not modify thresholds, does
not access anything outside the three tools, and does not handle more than one
exception per invocation. One agent, one job, per the scope contract.
3.6 Triage Report and Operator Output
Per exception: the validated JSON record plus a rendered human-readable report
(markdown/HTML) containing the same content.
Per run: a queue summary: counts by severity, the escalation list, and pointers to
every individual record including non-escalated ones. Nothing is hidden; the
summary orders attention.
3.7 API Layer
FastAPI, mirroring the FraudShield service pattern. Endpoints (final signatures in the
TRD): trigger a pipeline run, fetch the exception queue, fetch a triage record, triage a single
exception on demand, and health. The API exists because the deliverable is a service, not a
notebook, and because latency is a first-class harness metric that needs a service boundary
to be meaningful.
3.8 Evaluation Harness
A separate module that treats the system as a black box: it runs the full chain on held-out
test engines and measures prediction quality (accuracy, precision and recall on the critical
class), triage latency, escalation selectivity, and structural completeness of triage records.
Full specification, including exactly how the critical class is defined from true RUL and how
misses are itemized per engine, belongs to the TRD. The harness is the only source of any
performance claim this project will ever make.
4. Data Flow, End to End
1. Raw FD001 files land in .
data/raw/
2. Ingestion validates them, computes training RUL labels, writes canonical Parquet to
.
data/canonical/
3. Feature engineering reads canonical Parquet, fits its parameters on training units,
writes feature matrices.
4. Training (offline, documented, reproducible by script) fits the baseline and champion
candidate; the selected model is serialized with its feature version.
5. A pipeline run loads the model, predicts RUL for each test engine at its latest cycle,
and hands predictions to the exception generator.
6. The generator emits exception objects for Critical and Warning engines.
7. The triage agent processes each exception through its tools and emits a validated
triage record; guardrails enforce fail-safe behavior.
8. Reports render; the queue summary orders the operator's attention; everything is
written to (and to GCS when running deployed).
outputs/
9. The harness executes steps 5 through 8 on held-out engines and scores the whole
chain.
5. Technology Choices and Rationale
Choice Selection Rationale
Language Python 3.11+ The portfolio's proven language; entire ML
ecosystem
Data store Parquet (local canonical), GCS Durable source of truth, zero infrastructure
when deployed locally; pattern validated in DemoRAG
Modeling scikit-learn + gradient boosting Direct reuse of the ReneWind toolchain and
baseline; Keras/TensorFlow discipline
champion candidate
Agent LLM Gemini on Vertex AI GCP-native per locked decision; one cloud,
one bill
Service FastAPI Proven in FraudShield; async-friendly;
typed request/response models double as
schema enforcement
Validation Pydantic schemas everywhere data Makes the agent's output machine-
crosses a boundary checkable and the guardrails enforceable
Packaging Docker Identical behavior locally and on Cloud Run
Deployment Cloud Run, scripted with minimal Reuses the FraudShield infrastructure
Terraform pattern; spun up for demos, torn down after,
per the locked budget decision
Orchestration Plain Python entry points (no A four-stage batch pipeline does not justify
Airflow, no Prefect) an orchestrator; adding one would be scope
creep in tooling form
6. Key Design Tradeoffs
1. RUL regression thresholded into severity, versus direct failure classification. Chosen:
regression then threshold. It preserves the information an operator actually plans with
(how many cycles remain, not just "bad"), keeps severity policy separate from the model,
and reuses the ReneWind cost-asymmetric thresholding on top. Cost: two things to tune
(model and thresholds) instead of one, and the classification metrics in the harness depend
on threshold placement. The TRD handles this by fixing thresholds before test-set
evaluation.
2. Single agent with read-only tools, versus multi-agent or write-capable designs.
Chosen: single agent, read-only tools. Multi-agent adds coordination failure modes with no
benefit at this scope, and write access (adjusting thresholds, filing work orders) would
make the agent's mistakes operationally expensive. Cost: the agent is less impressive as a
demo of agentic maximalism. That is deliberate; the brand argument is that bounded,
trustworthy agents ship and get adopted.
3. LLM after the model, never as the predictor. Chosen: the LLM never sees raw sensor
math as a prediction task. LLMs are unreliable numerical predictors and using one there
would be indefensible in front of a technical interviewer. Cost: the system needs both a
trained model and an agent, which is more moving parts than an LLM-only demo. The parts
are the point.
4. Fail-safe escalation on agent failure. Chosen: any agent failure escalates the exception.
Cost: an agent outage floods the operator queue, which is exactly the pre-SustainAI status
quo. Failing back to the status quo is acceptable; failing into silence is not.
5. Batch execution with a service wrapper, versus streaming. Chosen: batch canonical,
service available. Streaming would demonstrate infrastructure already proven in
FraudShield while adding nothing to the triage story, and C-MAPSS is not streaming data.
Honest fit over impressive mismatch.
6. No dashboard. Chosen: structured reports only, per the locked scope decision. The
rendered report is designed to be screenshot-ready for the build log, which covers the
presentation need without a UI build.
7. Deployment View
Local (canonical): or plain venv; pipeline runs by CLI entry point;
docker compose
API by uvicorn; harness by a single command. Everything reproducible from a clean
clone with one documented setup script.
Demo (transient): minimal Terraform stands up Cloud Run with the same container,
GCS bucket for artifacts, Vertex AI reached via service account. Torn down after the
demo. Estimated steady-state cost when torn down: zero.
Secrets and config: environment variables locally, Secret Manager when deployed; no
credentials in the repo, ever.
8. What the SDD Hands to the TRD
The TRD must pin down: the Parquet and exception schemas, the exact RUL cap value, the
severity threshold values and the procedure for fixing them before test evaluation, the
critical-class definition from true RUL, the triage record schema and its validation rules, API
signatures, the full metric definitions and measurement procedures (including latency
measurement points), provisional numeric targets and the single-revision rule from the
BRD, and the acceptance criteria that define done.