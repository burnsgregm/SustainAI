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
