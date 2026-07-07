# SustainAI TRD Deviations

This file documents all currently unresolved deviations from the TRD (Technical Requirements Document) and associated directives.

- **Champion Fallback Substitution:** TensorFlow was removed due to a native Windows DLL initialization failure (see `docs/decisions.md` item 7). The system uses the pre-authorized `MLPRegressor` fallback for FR-MOD-2.
- **Vertex Schema Enforcement Substitution:** The hardcoded `response_schema` parameter injection into `VertexAI.GenerativeModel` was removed due to strict OpenAPI constraint failures. The pipeline now explicitly specifies `response_mime_type: application/json` and validates the returned payload via `TriageRecord` Pydantic models downstream.
