"""SustainAI deterministic stub agent.

Boundary: replaces the LLM with a deterministic rule-based stub that produces
schema-valid triage records. Replaces live AI calls in tests and local CI.
Implements TRD Section 8.8 (FR-STB-1).
"""

from __future__ import annotations

import uuid

from sustainai.config import get_config
from sustainai.schemas import (
    ActionType,
    ContextSummary,
    EngineInfo,
    EscalationDecision,
    ExceptionObject,
    RecommendedAction,
    SeverityAssessment,
    SeverityBand,
    TriageMeta,
    TriageRecord,
    AgentMode,
    FailureMode
)
from datetime import datetime, timezone
from sustainai.agent.tools import get_sensor_trends, get_degradation_history, get_fleet_summary

def run_stub_triage(exc: ExceptionObject) -> TriageRecord:
    """Run a deterministic triage for an exception."""
    cfg = get_config()
    
    # 1. Gather context via tools (proves tools can be called)
    # The tools are read-only and return simple Pydantic models.
    # We call them just to satisfy coverage and timing if needed.
    trends = get_sensor_trends(exc.unit_id)
    hist = get_degradation_history(exc.unit_id)
    fleet = get_fleet_summary()
    
    # Simple rule for escalation (FR-STB-1)
    is_critical = exc.severity_band == SeverityBand.CRITICAL
    near_critical = exc.predicted_rul <= (exc.thresholds_used.critical_max + 5)
    
    escalate = bool(is_critical or near_critical)
    
    if escalate:
        action = ActionType.PRIORITIZE_MAINTENANCE
        details = "Stub: Condition warrants immediate escalation."
    else:
        action = ActionType.SCHEDULE_INSPECTION
        details = "Stub: Condition stable enough for scheduled review."
        
    record = TriageRecord(
        triage_id=str(uuid.uuid4()),
        exception_id=exc.exception_id,
        engine=EngineInfo(
            unit_id=exc.unit_id,
            predicted_rul=exc.predicted_rul,
            severity_band=exc.severity_band.value
        ),
        severity_assessment=SeverityAssessment(
            agrees_with_band=True,
            assessed_band=exc.severity_band,
            reasoning="Stub automatically agrees with mathematical band assigned by pipeline."
        ),
        context=ContextSummary(
            sensor_trend_summary=f"Stub gathered {len(trends.trends)} sensor trends.",
            degradation_summary=f"Stub observed {hist.cycles_observed} cycles.",
            fleet_position=f"Stub noted {fleet.total_units} units in run.",
            tool_calls_made=3
        ),
        recommended_action=RecommendedAction(
            action_type=action,
            horizon_cycles=int(exc.predicted_rul),
            details=details
        ),
        escalation=EscalationDecision(
            escalate=escalate,
            rationale="Stub: escalated based on deterministic proximity rule."
        ),
        meta=TriageMeta(
            agent_mode=AgentMode.STUB,
            agent_model="deterministic_stub_v1",
            latency_ms=15,  # Fixed small latency for stub
            failure_mode=FailureMode.NONE,
            created_at=datetime.now(timezone.utc)
        )
    )
    
    return record
