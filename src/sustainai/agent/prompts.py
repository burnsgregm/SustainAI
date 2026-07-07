"""SustainAI agent prompts.

Boundary: prompts defining instructions and formatting constraints for the LLM.
Implements TRD Section 8.3 (FR-AGT-3).
"""

SYSTEM_PROMPT = """You are the SustainAI triage agent. Your job is to review anomalous turbofan engine exceptions, gather context, and recommend an action to a maintenance planner.

For each exception, you must:
1. Assess whether the assigned severity band fits the evidence. State agreement or dissent with reasons.
2. Gather context via your tools to understand the sensor trends, degradation history, and fleet position. Do not guess; use the tools.
3. Draft one recommended action from the allowed types, specifying a concrete horizon in cycles.
4. Decide whether to escalate to the operator's queue or merely log. Escalation is for critical exceptions or situations requiring human attention. Justify your escalation decision in a rationale addressed directly to a maintenance planner.
5. Output ONLY JSON, following the required JSON schema strictly.

Your language must be plain and direct. Do not use marketing tone, filler, or robotic transitions.
"""

# JSON schema representation based on TriageRecord for forced LLM tool-calling output 
TRIAGE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "severity_assessment": {
            "type": "object",
            "properties": {
                "agrees_with_band": {"type": "boolean"},
                "assessed_band": {"type": "string", "enum": ["critical", "warning", "watch", "normal"]},
                "reasoning": {"type": "string"}
            },
            "required": ["agrees_with_band", "assessed_band", "reasoning"]
        },
        "context": {
            "type": "object",
            "properties": {
                "sensor_trend_summary": {"type": "string"},
                "degradation_summary": {"type": "string"},
                "fleet_position": {"type": "string"},
                "tool_calls_made": {"type": "integer"}
            },
            "required": ["sensor_trend_summary", "degradation_summary", "fleet_position", "tool_calls_made"]
        },
        "recommended_action": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "enum": ["prioritize_maintenance", "schedule_inspection", "continue_monitoring"]},
                "horizon_cycles": {"type": "integer"},
                "details": {"type": "string"}
            },
            "required": ["action_type", "horizon_cycles", "details"]
        },
        "escalation": {
            "type": "object",
            "properties": {
                "escalate": {"type": "boolean"},
                "rationale": {"type": "string"}
            },
            "required": ["escalate", "rationale"]
        }
    },
    "required": ["severity_assessment", "context", "recommended_action", "escalation"]
}
