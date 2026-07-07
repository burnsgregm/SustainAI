SustainAI: Business Requirements Document (BRD)
Project: SustainAI, Predictive Sustainment and Supply-Exception Triage (working name)
Author: Gregory Burns Version: 0.1 (Draft) Date: July 6, 2026 Status: In development. This
document describes a system being built. No results are claimed anywhere in this
document. All performance figures are targets or placeholders pending output from the
evaluation harness defined in the TRD.
1. Executive Summary
SustainAI is a predictive-sustainment and supply-exception-triage system. It ingests real
public sensor data from degrading turbofan engines (NASA C-MAPSS), predicts which
engines are approaching failure, converts those predictions into a queue of exceptions, and
applies a single AI agent to triage each exception: assess severity, gather context, draft a
recommended action, and escalate only what a human needs to see.
The system exists to solve one problem: an operator drowning in exceptions cannot tell
which ones threaten the mission. Prediction alone does not solve this; a model that flags 40
engines produces 40 new items on an already overloaded queue. SustainAI pairs prediction
with a decision-support action the operator can trust, so the human sees a short, prioritized,
justified list instead of a raw alert stream.
SustainAI is a demonstration system built on public simulated data. It is not deployed
against a live fleet and does not claim to be. Its purpose is to prove, end to end and with
honest measurement, that the pattern works: predict, triage, escalate selectively, and
evaluate the whole chain.
2. The Operator Problem
Logisticians and maintenance planners drown in exceptions: late shipments, parts
shortfalls, maintenance flags, demand spikes. Most are routine. A few are mission-critical.
The scarce resource is not data; it is the operator's attention and judgment. Today the triage
burden falls entirely on the human, who must scan every flag, chase context across
systems, decide severity, and choose an action, all under time pressure.
The failure modes of the status quo are well known to anyone who has stood in a
maintenance or embarkation shop:
Alert fatigue. When everything is flagged, nothing is. Operators learn to ignore the
queue, and the one critical exception drowns with the routine ones.
Context chasing. Deciding whether a flag matters requires pulling history, current
status, and operational context from multiple places. Each lookup costs minutes the
operator does not have.
Inconsistent triage. Two operators, or the same operator at hour one versus hour ten
of a shift, will triage the same exception differently. There is no documented,
repeatable reasoning behind the decision.
Late escalation. The critical exception is discovered when the failure happens, not
before, because it never rose above the noise.
The reference scenario for this build: a sustainment cell monitoring a fleet of turbofan
engines. Sensor data indicates gradual degradation. The cell needs to know which engines
need attention now, which need scheduling, and which can wait, and it needs the reasoning
behind each call, not just a score.
3. Why This System, and Why Now
Predictive maintenance is a solved pattern at the model level. The prior project ReneWind
demonstrated it: a classifier tuned against asymmetric business costs (a missed failure
costs a replacement, a false alarm costs an inspection). What remains unsolved in most
deployments is the last mile: turning a prediction into a decision a human can act on
without doing all the analytical work themselves.
SustainAI extends the proven predictive-maintenance pattern with an agentic triage layer.
The bet it demonstrates is narrow and testable: a single agent doing one bounded job
(triage) can reduce the operator's queue to only what genuinely needs human judgment,
with a drafted recommendation and documented reasoning attached, without hiding
anything the human is entitled to see.
4. Business Objectives
# Objective What it means concretely
BO- Reduce operator The operator reviews a short, prioritized escalation list, not the full
1 triage load exception stream. The full stream remains inspectable; the agent
filters attention, it does not hide data.
BO- Catch critical Engines approaching failure are surfaced with enough remaining
2 exceptions early useful life for planned intervention rather than reactive replacement.
BO- Make triage Every triage decision carries the same structure: severity assessment,
3 consistent and context gathered, recommended action, escalation rationale. Two
auditable identical exceptions get consistent treatment, and every decision can
be reviewed after the fact.
BO- Earn trust through The system ships with an evaluation harness measuring prediction
4 measurement quality (accuracy, precision and recall on the critical class) and triage
# Objective What it means concretely
responsiveness (latency). No claim is made that the harness has not
produced.
5. Stakeholders and Users
Primary user: the sustainment operator (maintenance planner). The person who owns
the exception queue. Needs: fewer items demanding attention, each with severity, context,
and a recommended action attached, and the ability to see the agent's reasoning and
override it.
Secondary user: the maintenance control lead. The person accountable for fleet readiness.
Needs: confidence that escalations are consistent and that nothing critical is being silently
filtered. Reviews the audit trail, not the live queue.
System owner / builder: responsible for the pipeline, the model, the agent, and the honesty
of the evaluation. In this build, a single engineer.
Reviewing audience (acknowledged openly): this is a portfolio system. Hiring managers
and technical interviewers will read these documents and the results. This audience is
served by the same thing that serves the operator: rigor, honesty, and a system that works
end to end. Nothing in the design exists purely for show.
6. Scope
6.1 In scope
1. One dataset. NASA C-MAPSS turbofan engine degradation, subset FD001 only
(single operating condition, single fault mode). FD001 is chosen deliberately as the
scope-disciplined starting point; the harder subsets are explicitly out of scope for v1.
2. One end-to-end pipeline. Ingest FD001 sensor data, predict remaining useful life
(RUL) per engine, threshold predictions into severity bands, and emit exceptions for
engines crossing the critical threshold.
3. One agent doing one job. For each exception: assess severity, gather context from the
pipeline's own outputs (sensor trends, degradation history, fleet position), draft a
recommended action, and decide escalate versus log. Nothing else. The agent does
not retrain models, does not manage inventory, does not talk to external systems.
4. One evaluation harness. Measures prediction accuracy, precision and recall on the
critical class, and triage latency. Defined fully in the TRD. Designed to reveal failure,
not just confirm success.
5. Operator output. A structured triage report per exception (severity, context,
recommended action, escalation decision, reasoning), delivered as an API response
and a rendered report file.
6.2 Out of scope (explicit, by decision)
C-MAPSS subsets FD002, FD003, FD004, and any second dataset
Any dashboard or web UI (candidate for a future iteration, documented as such)
Multi-agent architectures, agent-to-agent communication, or agents with more than
the one triage job
Live or always-on hosted deployment (the Cloud Run deployment is scripted and
documented; it is spun up for demonstrations, not left running)
Inventory, procurement, or work-order system integration
Retraining pipelines, drift monitoring, or model lifecycle automation (proven
elsewhere in the portfolio by FraudShield; not rebuilt here)
Real-time streaming ingestion (C-MAPSS is batch by nature; the pipeline processes it
as batch with per-exception triage)
Any proposed addition during the build is tested against one question: does the committed
scope on the public project page require it? If not, it goes to the "next iteration" list.
7. Success Criteria and How Success Is Measured
Success is defined by the evaluation harness, not by narrative. The harness and its exact
measurement procedures are specified in the TRD. At the BRD level, success means:
# Criterion Measured by
SC- The pipeline runs end to end on FD001: Harness executes the full chain and reports
1 ingest to prediction to exception to triage completion
report, with no manual intervention
SC- Prediction quality on the critical class meets Precision and recall on the critical class,
2 or exceeds the provisional targets set in the measured on held-out test engines
TRD
SC- Triage is responsive enough for an operator Per-exception triage latency, measured by
3 workflow the harness (target set in TRD)
SC- Escalation is selective and justified Fraction of exceptions escalated versus
4 logged, and presence of complete reasoning
in every triage report
SC- The system's failures are visible The harness reports misses (critical engines
5 not flagged) and false alarms explicitly, per
engine, not just as aggregates
Integrity note on targets. Provisional numeric targets (for example, a recall floor on the
critical class) are set in the TRD before modeling begins and may be revised once against a
documented baseline, with the revision and its reason recorded. Targets are commitments
to measure against, not results. No number moves from "target" to "achieved" anywhere in
the portfolio until the harness produces it on held-out data.
8. Assumptions and Constraints
Assumptions
FD001 provides sufficient signal to build a meaningful RUL predictor; this is well
established in the predictive-maintenance literature and is the reason C-MAPSS is the
gold standard.
The ReneWind pattern (threshold optimization against asymmetric cost) transfers to
the RUL-to-severity thresholding problem.
A single agent with access to pipeline outputs has enough context to produce useful
triage; no external data sources are needed for the demonstration.
Constraints
Builder: one engineer, part-time, alongside an active job search. The scope cap exists
partly because of this constraint.
Budget: near zero ongoing cost. Local-first execution; cloud resources used
transiently for demonstrations. The agent's LLM calls (Vertex AI, Gemini) are the
main variable cost and are bounded by the batch nature of the data.
Stack: GCP, Python, FastAPI, and the patterns already proven in ReneWind,
FraudShield, and DemoRAG. New tooling is admitted only when the existing stack
genuinely cannot do the job.
Honesty: the public project page states that no results will be claimed until the
harness produces them. That constraint binds this document and everything
downstream.
9. Risks
Risk Impact Mitigation
Scope creep (second Build never ships; Section 6.2 is the contract. Additions go to the
dataset, dashboard, violates the strategy's "next iteration" list by default.
multi-agent) core rule
Risk Impact Mitigation
Agent triage quality is The differentiating TRD defines concrete, checkable triage criteria
hard to evaluate layer lacks credible (structural completeness, escalation consistency,
objectively measurement latency) rather than vague "quality" scores.
Prediction metrics stay cleanly separated from
triage metrics.
RUL model Weak headline Report honestly, analyze why, document the
underperforms numbers tradeoffs. An honest miss with analysis is on-
provisional targets brand; a fudged hit is fatal to the brand.
LLM cost or latency Blows the budget or Bound context size per exception; cap tokens;
spikes during triage the latency target measure latency in the harness from day one.
Build competes with Violates "deploy, Build proceeds only alongside a running weekly
job-search execution don't build" scorecard, per the locked portfolio plan.
sequencing
10. Deliverables
1. This BRD (approved)
2. System Design Document (SDD)
3. Technical Requirements Document (TRD), including the evaluation harness
specification and acceptance criteria that define "done"
4. The working system: pipeline, model, agent, harness, and operator triage reports
5. Documentation of design decisions and tradeoffs as the build proceeds (doubles as
build-log content for the public project page)
11. Glossary
C-MAPSS: Commercial Modular Aero-Propulsion System Simulation. NASA's
simulated turbofan engine degradation dataset; FD001 is its simplest subset.
RUL: Remaining Useful Life. The number of operational cycles an engine has left
before failure.
Exception: An engine whose predicted RUL crosses a defined severity threshold,
requiring triage.
Critical class: Engines whose true RUL is below the critical threshold; the class the
system must not miss.
Triage: The agent's single job: assess severity, gather context, draft a recommended
action, decide escalate versus log.
Escalation: Placing an exception on the short list a human must review.
Evaluation harness: The fixed measurement procedure that produces every
performance claim the project makes.