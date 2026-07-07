# SustainAI TRD Deviations

This file documents all currently unresolved deviations from the TRD (Technical Requirements Document) and associated directives.

- **Champion Fallback Substitution:** TensorFlow was removed due to a native Windows DLL initialization failure (see `docs/decisions.md` item 7). The system uses the pre-authorized `MLPRegressor` fallback for FR-MOD-2.
- **Live Vertex Implementation:** The codebase includes a live Vertex AI implementation. It is marked `UNVERIFIED-LIVE` because it has not yet been executed with valid credentials.
