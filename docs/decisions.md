# SustainAI - TBD-EMPIRICAL and PROVISIONAL Decisions Log

This document records the empirical bounds and provisional choices discovered and bound during the autonomous build phase.

## 1. Data Source URL
**Status:** PROVISIONAL.
The C-MAPSS dataset mirror originally attempted via NASA legacy links was out-of-date/unavailable. We manually fetched it using standard dataset archives. The data was sourced locally from standard CMAPSS Data mirrors into `data/raw/` via standard archive extraction to bypass link decay.

## 2. Empirical Variance Drops
**Status:** PROVISIONAL.
As observed in the AC-1 automation traces, the near-constant variance filter explicitly identified that `sensor_06` was inherently retained natively, while `op_setting_2` and `op_setting_3` were successfully dropped along with `sensor_01`, `sensor_10`, `sensor_16`, `sensor_18`, and `sensor_19` (8 features total dropped).

## 3. Operational Setting Features
**Status:** IMPLEMENTED (Priority 5.5).
Operational setting columns (`op_setting_1-3`) are included dynamically through identical variance filters and cyclic aggregates.

## 4. Minimum Target Recall / Precision constraints
**Status:** TBD.
The AC-1 pipeline trace (`eval-24243a5a`) measured critical recall at 0.8421 against the 0.80 floor. It measured critical precision at 0.9412 against the 0.65 floor. Both metrics PASS the TRD targets.

## 5. Threshold Revisions
**Status:** PROVISIONAL.
The tuning logic evaluated thresholds on the validation set (`threshold_report.json`). The sweep produced nonzero costs across most candidates, reached cost 0 at 25 and 26, and the tie-break kept the provisional 25.

## 6. Validation Data Simulation (Truncation)
**Status:** PROVISIONAL.
The validation dataset employs deterministic random cycle truncation to simulate mid-life conditions. The features script generates K=5 distinct seeded targets to expand the 20 test slices.

## 7. Build Execution Environment
**Status:** CONSTRAINED.
The build environment is pinned to Python >=3.10 and <3.13 due to pyarrow C bindings on Windows. TensorFlow failed to load the DllMain library inside pytest due to AVX incompatibilities. We used the pre-authorized MLPRegressor fallback model.

## 8. Agent Configuration Limits
**Status:** PROVISIONAL.
The `agent.max_output_tokens` value was raised from its initial bound to resolve live-mode JSON truncation and is pinned at its current value to support the full 4-block structured TriageRecord JSON output without dropping content.

## 9. AC-4 Live Gemini Verification
**Status:** COMPLETE.
Live triage executed against Vertex AI (gemini-2.5-flash, us-central1) on all 33 test-set exceptions. Eval ID: eval-3477d2bf. Results: 0.0 failure rate, 100% schema validity, latency p50 8,839 ms / p95 11,995 ms (target 15,000 ms: PASS). Two config/prompt fixes were required and are recorded here: (a) agent.max_output_tokens raised to 4096 after live-mode JSON truncation; (b) SYSTEM_PROMPT extended to pin the exact output-contract field names after the model initially emitted non-schema field names. Guardrail FR-GRD-1 was observed working correctly on Unit 81, where the agent assessed a model-flagged critical engine as low-risk and recommended continue_monitoring, and the guardrail forced escalation anyway (forced_by_guardrail=true), preserving the agent's dissent for the operator.

## 10. Vertex Cost
**Status:** PRELIMINARY.
Billing showed $0.00 as of Jul 7 (usage not yet settled). 33 Gemini 2.5 Flash calls expected in low single-digit cents. Final figure pending settlement; update when billing posts.