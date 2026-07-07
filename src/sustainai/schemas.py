"""SustainAI data schemas.

Boundary: defines every Pydantic model used across component boundaries.
All data crossing a module boundary must conform to one of these models.
Implements TRD Section 6 in full.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Split(str, enum.Enum):
    """Dataset split identifier."""
    TRAIN = "train"
    VAL = "val"
    TEST = "test"


class SeverityBand(str, enum.Enum):
    """Severity band for an engine based on predicted RUL."""
    CRITICAL = "critical"
    WARNING = "warning"
    WATCH = "watch"
    NORMAL = "normal"


class ActionType(str, enum.Enum):
    """Closed enum of recommended actions the triage agent may propose."""
    PRIORITIZE_MAINTENANCE = "prioritize_maintenance"
    SCHEDULE_INSPECTION = "schedule_inspection"
    CONTINUE_MONITORING = "continue_monitoring"


class FailureMode(str, enum.Enum):
    """How the agent invocation failed, if at all."""
    NONE = "none"
    TIMEOUT = "timeout"
    MALFORMED_OUTPUT = "malformed_output"
    TOOL_ERROR = "tool_error"


class AgentMode(str, enum.Enum):
    """Whether the agent is using a live LLM or the deterministic stub."""
    LIVE = "live"
    STUB = "stub"


# ---------------------------------------------------------------------------
# 6.1 Canonical record (Parquet schema)
# ---------------------------------------------------------------------------

class CanonicalRecord(BaseModel):
    """One row of the canonical Parquet dataset.

    Covers train, val and test splits. RUL is present for train/val rows;
    true_rul_final is present only for the final cycle of each test unit.
    """
    unit_id: int
    cycle: int
    op_setting_1: float
    op_setting_2: float
    op_setting_3: float
    sensor_01: float
    sensor_02: float
    sensor_03: float
    sensor_04: float
    sensor_05: float
    sensor_06: float
    sensor_07: float
    sensor_08: float
    sensor_09: float
    sensor_10: float
    sensor_11: float
    sensor_12: float
    sensor_13: float
    sensor_14: float
    sensor_15: float
    sensor_16: float
    sensor_17: float
    sensor_18: float
    sensor_19: float
    sensor_20: float
    sensor_21: float
    rul: Optional[int] = None
    true_rul_final: Optional[int] = None
    split: Split


# Column names expected in the raw C-MAPSS files (26 columns).
RAW_COLUMNS: list[str] = (
    ["unit_id", "cycle"]
    + [f"op_setting_{i}" for i in range(1, 4)]
    + [f"sensor_{i:02d}" for i in range(1, 22)]
)

assert len(RAW_COLUMNS) == 26, f"Expected 26 raw columns, got {len(RAW_COLUMNS)}"


# ---------------------------------------------------------------------------
# 6.2 Prediction record
# ---------------------------------------------------------------------------

class PredictionRecord(BaseModel):
    """Output of the prediction service for a single engine at its latest cycle."""
    unit_id: int
    cycle: int
    predicted_rul: float = Field(ge=0)
    model_id: str
    feature_version: str
    run_id: str
    created_at: datetime


# ---------------------------------------------------------------------------
# 6.3 Exception object
# ---------------------------------------------------------------------------

class ThresholdsUsed(BaseModel):
    """Snapshot of the severity thresholds at the time the exception was generated."""
    critical_max: int
    warning_max: int
    watch_max: int


class ExceptionObject(BaseModel):
    """An exception generated for an engine that crossed the critical or warning threshold."""
    exception_id: str  # uuid4
    run_id: str
    unit_id: int
    predicted_rul: float
    severity_band: SeverityBand  # only critical or warning
    thresholds_used: ThresholdsUsed
    model_id: str
    created_at: datetime

    @field_validator("severity_band")
    @classmethod
    def severity_must_be_actionable(cls, v: SeverityBand) -> SeverityBand:
        if v not in (SeverityBand.CRITICAL, SeverityBand.WARNING):
            raise ValueError(f"Exceptions are only emitted for critical/warning, got {v}")
        return v


# ---------------------------------------------------------------------------
# 6.4 Triage record (the agent's output contract)
# ---------------------------------------------------------------------------

class EngineInfo(BaseModel):
    """Engine snapshot embedded in a triage record."""
    unit_id: int
    predicted_rul: float
    severity_band: str


class SeverityAssessment(BaseModel):
    """The agent's assessment of whether the severity band is appropriate."""
    agrees_with_band: bool
    assessed_band: SeverityBand
    reasoning: str = Field(min_length=1, max_length=1200)


class ContextSummary(BaseModel):
    """Context gathered by the agent via its read-only tools."""
    sensor_trend_summary: str = Field(min_length=1, max_length=1200)
    degradation_summary: str = Field(min_length=1, max_length=1200)
    fleet_position: str = Field(min_length=1, max_length=600)
    tool_calls_made: int = Field(ge=0)


class RecommendedAction(BaseModel):
    """The agent's recommended action for the exception."""
    action_type: ActionType
    horizon_cycles: int = Field(ge=0)
    details: str = Field(min_length=1, max_length=1200)


class EscalationDecision(BaseModel):
    """Whether the exception should be escalated to the operator."""
    escalate: bool
    forced_by_guardrail: bool = False
    rationale: str = Field(min_length=1, max_length=1200)


class TriageMeta(BaseModel):
    """Metadata about the triage invocation."""
    agent_mode: AgentMode
    agent_model: str
    latency_ms: int = Field(ge=0)
    failure_mode: FailureMode = FailureMode.NONE
    schema_version: str = "1.0"
    created_at: datetime


class TriageRecord(BaseModel):
    """Complete triage record for a single exception.

    This is the agent's output contract per TRD Section 6.4.
    Validation is mandatory — a record that fails validation after the
    permitted retry is replaced by the fail-safe record.
    """
    triage_id: str  # uuid4
    exception_id: str
    engine: EngineInfo
    severity_assessment: SeverityAssessment
    context: ContextSummary
    recommended_action: RecommendedAction
    escalation: EscalationDecision
    meta: TriageMeta


# ---------------------------------------------------------------------------
# 6.5 Queue summary (per run)
# ---------------------------------------------------------------------------

class EscalationListItem(BaseModel):
    """One entry on the operator's escalation list."""
    unit_id: int
    predicted_rul: float
    severity_band: str
    action_type: str
    triage_id: str


class BandCounts(BaseModel):
    """Counts of engines by severity band for the entire run."""
    critical: int = 0
    warning: int = 0
    watch: int = 0
    normal: int = 0


class QueueSummary(BaseModel):
    """Summary of a complete pipeline run's triage results."""
    run_id: str
    created_at: datetime
    engines_processed: int
    counts_by_band: BandCounts
    exceptions_total: int
    escalated: int
    logged_only: int
    guardrail_forced: int
    agent_failures: int
    escalation_list: list[EscalationListItem]
    all_records_index: list[str]  # triage_ids


# ---------------------------------------------------------------------------
# Tool return types (Section 8.2)
# ---------------------------------------------------------------------------

class SensorTrendPoint(BaseModel):
    """A single sensor's trend data."""
    sensor_name: str
    recent_values: list[float]
    direction: str  # increasing, decreasing, stable
    rate_vs_baseline: float  # ratio vs unit's own early-life baseline


class SensorTrends(BaseModel):
    """Return type for get_sensor_trends tool."""
    unit_id: int
    last_n_cycles: int
    trends: list[SensorTrendPoint]


class DegradationHistory(BaseModel):
    """Return type for get_degradation_history tool."""
    unit_id: int
    cycles_observed: int
    current_predicted_rul: float
    rul_trajectory: list[float]  # predicted RUL at each observed cycle


class FleetSummary(BaseModel):
    """Return type for get_fleet_summary tool."""
    counts_by_band: BandCounts
    unit_percentile: float = Field(ge=0, le=100)
    total_units: int


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------

class RunResponse(BaseModel):
    """Response when a pipeline run is triggered."""
    run_id: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    model_id: str
    agent_mode: str
    schema_version: str


class ErrorResponse(BaseModel):
    """Structured error response."""
    error_code: str
    message: str
    detail: Optional[str] = None
