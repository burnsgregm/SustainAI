"""SustainAI queue summary and reporting.

Boundary: aggregates triage records into a QueueSummary for ops consumption.
Implements TRD Section 6.5.
"""

from __future__ import annotations

import json
from pathlib import Path

from sustainai.schemas import QueueSummary, TriageRecord, BandCounts, EscalationListItem
from datetime import datetime, timezone

def generate_queue_summary(run_id: str, records: list[TriageRecord]) -> QueueSummary:
    """Generate the ops-level summary for a given run."""
    
    total = len(records)
    escalated = sum(1 for r in records if r.escalation.escalate)
    logged = total - escalated
    
    crit_count = sum(1 for r in records if r.engine.severity_band == "critical")
    warn_count = sum(1 for r in records if r.engine.severity_band == "warning")
    # Triage currently only operates on critical/warning per FR-EXC-2, but we tally them
    watch_count = sum(1 for r in records if r.engine.severity_band == "watch")
    norm_count = sum(1 for r in records if r.engine.severity_band == "normal")
    
    counts = BandCounts(
        critical=crit_count,
        warning=warn_count,
        watch=watch_count,
        normal=norm_count
    )
    
    # Calculate avg latency for valid records
    latencies = [r.meta.latency_ms for r in records if r.meta.latency_ms is not None]
    avg_lat = int(sum(latencies) / len(latencies)) if latencies else 0
    
    # Check failure events
    failure_events = sum(1 for r in records if r.meta.failure_mode != "none")
    
    guardrail_forced = sum(1 for r in records if r.escalation.forced_by_guardrail)
    
    escalation_list = []
    all_records = []
    
    for r in records:
        all_records.append(r.exception_id)
        if r.escalation.escalate:
            escalation_list.append(EscalationListItem(
                unit_id=r.engine.unit_id,
                predicted_rul=r.engine.predicted_rul,
                severity_band=r.engine.severity_band,
                action_type=r.recommended_action.action_type.value,
                triage_id=r.triage_id
            ))
            
    summary = QueueSummary(
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
        engines_processed=total,
        exceptions_total=total,
        counts_by_band=counts,
        escalated=escalated,
        logged_only=logged,
        guardrail_forced=guardrail_forced,
        agent_failures=failure_events,
        escalation_list=escalation_list,
        all_records_index=all_records
    )
    
    return summary


def write_triage_artifacts(out_dir: Path, records: list[TriageRecord], summary: QueueSummary) -> None:
    """Write triage records and run summary to disk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    
    triage_file = out_dir / "triage.json"
    with open(triage_file, "w") as f:
        json.dump([r.model_dump(mode='json') for r in records], f, indent=2)
        
    summary_file = out_dir / "run_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary.model_dump(mode='json'), f, indent=2)

    # Priority 4.2: Render formatted markdown operator reports
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Run-level queue summary
    summary_md = f"# Queue Summary (Run: {summary.run_id})\n\n"
    summary_md += f"**Generated:** {summary.created_at}\n"
    summary_md += f"**Processed:** {summary.engines_processed} | **Escalated:** {summary.escalated} | **Agent Failures:** {summary.agent_failures}\n\n"
    
    summary_md += "## Escalation List\n"
    if summary.escalation_list:
        for esc in summary.escalation_list:
            summary_md += f"- **Unit {esc.unit_id}**: {esc.severity_band} (RUL: {esc.predicted_rul}) -> **{esc.action_type}** | [Triage ID: {esc.triage_id}]\n"
    else:
        summary_md += "No escalations.\n"
        
    summary_md += "\n## Metrics\n"
    summary_md += f"- **Critical:** {summary.counts_by_band.critical}\n"
    summary_md += f"- **Warning:** {summary.counts_by_band.warning}\n"
    summary_md += f"- **Normal:** {summary.counts_by_band.normal}\n"
    
    with open(reports_dir / "queue_summary.md", "w") as f:
        f.write(summary_md)
        
    # 2. One report per exception
    for r in records:
        rmd = f"# Triage Report: Unit {r.engine.unit_id}\n\n"
        rmd += f"**Severity:** {r.engine.severity_band} (Predicted RUL: {r.engine.predicted_rul})\n"
        rmd += f"**Exception ID:** {r.exception_id}\n\n"
        
        rmd += "## Severity Assessment\n"
        rmd += f"**Agrees with Band:** {r.severity_assessment.agrees_with_band}\n"
        rmd += f"**Assessed Band:** {r.severity_assessment.assessed_band.value}\n"
        rmd += f"**Reasoning:** {r.severity_assessment.reasoning}\n\n"
        
        rmd += "## Context Summary\n"
        rmd += f"**Sensor Trends:** {r.context.sensor_trend_summary}\n"
        rmd += f"**Degradation:** {r.context.degradation_summary}\n"
        rmd += f"**Fleet Position:** {r.context.fleet_position}\n\n"
        
        rmd += "## Recommended Action\n"
        rmd += f"**Action Type:** {r.recommended_action.action_type.value}\n\n"
        rmd += f"{r.recommended_action.details}\n\n"
        
        rmd += "## Escalation Decision\n"
        rmd += f"**Escalate:** {r.escalation.escalate}\n"
        rmd += f"**Forced by Guardrail:** {r.escalation.forced_by_guardrail}\n\n"
        rmd += f"Reasoning: {r.escalation.rationale}\n"
        
        if r.meta.failure_mode != "none":
            rmd += f"\n## Agent Errors\nFailure Mode: {r.meta.failure_mode}\n"
            
        with open(reports_dir / f"exception_{r.exception_id}.md", "w") as f:
            f.write(rmd)
