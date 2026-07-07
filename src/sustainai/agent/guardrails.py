"""SustainAI triage guardrails.

Boundary: deterministically enforces rules on the agent's output.
Implements TRD Section 8.6 (FR-GRD-1, FR-GRD-2, FR-GRD-3).
"""

from __future__ import annotations

import logging

from sustainai.schemas import FailureMode, SeverityBand, TriageRecord

logger = logging.getLogger(__name__)


def apply_guardrails(record: TriageRecord) -> TriageRecord:
    """Apply safety overrides to the agent's triage decision.
    
    Returns the modified record in-place (or newly constructed).
    """
    
    # FR-GRD-2: Any failure_mode != none forces escalate = true
    if record.meta.failure_mode != FailureMode.NONE:
        if not record.escalation.escalate:
            logger.info("Guardrail [FR-GRD-2]: forcing escalation due to agent failure.")
            record.escalation.escalate = True
            record.escalation.forced_by_guardrail = True
        return record

    # FR-GRD-1: A Critical exception can never be silently downgraded to log-only.
    # If severity_band == critical and the agent sets escalate = false,
    # override to escalate = true, forced_by_guardrail = true.
    if record.engine.severity_band == SeverityBand.CRITICAL.value:
        if not record.escalation.escalate:
            logger.info("Guardrail [FR-GRD-1]: forcing escalation for critical engine.")
            record.escalation.escalate = True
            record.escalation.forced_by_guardrail = True
            # The agent's dissenting rationale is preserved verbatim automatically,
            # we just leave record.escalation.rationale untouched.
            
    return record


def create_failsafe_record(
    exception_id: str, 
    run_id: str, 
    unit_id: int, 
    predicted_rul: float, 
    severity_band: SeverityBand, 
    failure_mode: FailureMode,
    latency_ms: int,
    agent_mode: str,
    agent_model: str
) -> TriageRecord:
    """Create a guaranteed-valid record when the agent fails completely."""
    
    from sustainai.schemas import (
        ActionType,
        ContextSummary,
        EngineInfo,
        EscalationDecision,
        RecommendedAction,
        SeverityAssessment,
        TriageMeta,
    )
    from datetime import datetime, timezone
    
    record = TriageRecord(
        triage_id=f"fail-{uuid.uuid4().hex[:12]}",
        exception_id=exception_id,
        engine=EngineInfo(
            unit_id=unit_id,
            predicted_rul=predicted_rul,
            severity_band=severity_band.value
        ),
        severity_assessment=SeverityAssessment(
            agrees_with_band=True,
            assessed_band=severity_band,
            reasoning="triage unavailable"
        ),
        context=ContextSummary(
            sensor_trend_summary="triage unavailable",
            degradation_summary="triage unavailable",
            fleet_position="triage unavailable",
            tool_calls_made=0
        ),
        recommended_action=RecommendedAction(
            action_type=ActionType.PRIORITIZE_MAINTENANCE,
            horizon_cycles=int(predicted_rul),
            details="triage unavailable"
        ),
        escalation=EscalationDecision(
            escalate=True,
            forced_by_guardrail=True,
            rationale="triage unavailable"
        ),
        meta=TriageMeta(
            agent_mode=agent_mode,
            agent_model=agent_model,
            latency_ms=latency_ms,
            failure_mode=failure_mode,
            created_at=datetime.now(timezone.utc)
        )
    )
    
    return record


import uuid
