"""SustainAI main triage agent entrypoint.

Boundary: processes exception objects, calls either the live agent or stub,
applies deterministic guardrails, and handles logic for retries and timeouts.
Implements TRD Section 8.
"""

from __future__ import annotations

import logging
import time
import json
import concurrent.futures

from pydantic import ValidationError

from sustainai.config import get_config
from sustainai.schemas import AgentMode, ExceptionObject, FailureMode, TriageRecord
from sustainai.agent.guardrails import apply_guardrails, create_failsafe_record
from sustainai.agent.stub import run_stub_triage
from sustainai.agent.prompts import SYSTEM_PROMPT, TRIAGE_JSON_SCHEMA
from sustainai.agent.tools import get_agent_tools

logger = logging.getLogger(__name__)


def _call_vertex_ai(exc: ExceptionObject, validation_error: str | None = None) -> dict:
    """True shell for GCP Vertex AI (Gemini) payload logic.
    
    If validation_error is passed, this is a retry invocation per FR-AGT-4.
    """
    cfg = get_config()
    
    # Initialize the Vertex Model natively
    import vertexai
    from vertexai.generative_models import GenerativeModel
    
    prompt = SYSTEM_PROMPT.format(
        exception_id=exc.exception_id,
        unit_id=exc.unit_id,
        predicted_rul=exc.predicted_rul,
        severity_band=exc.severity_band
    )
    
    if validation_error:
        prompt += f"\n\nERROR PREVIOUS REQUEST WAS MALFORMED: {validation_error}\nPlease try again formatted strictly."
        
    model = GenerativeModel(cfg.gemini_model)
    
    response = model.generate_content(
        prompt,
        generation_config={
            "max_output_tokens": cfg.agent.max_output_tokens,
            "temperature": cfg.agent.temperature,
            "response_mime_type": "application/json",
        }
    )
    
    try:
        text = response.candidates[0].content.parts[0].text
        if not text:
            raise ValueError("Vertex returned empty text")
        return json.loads(text)
    except (IndexError, AttributeError) as e:
        raise ValueError(f"Unexpected response shape: {repr(e)}")


def run_live_triage(exc: ExceptionObject) -> TriageRecord:
    """Executes live LLM triage adhering to timeout and retry mechanisms."""
    cfg = get_config()
    
    def attempt_call(err_msg: str | None = None) -> TriageRecord:
        import uuid
        from datetime import datetime, timezone
        start_ts = time.time()
        raw_json = _call_vertex_ai(exc, validation_error=err_msg)
        latency = int((time.time() - start_ts) * 1000)
        
        assembled = {
            "triage_id": str(uuid.uuid4()),
            "exception_id": exc.exception_id,
            "engine": {
                "unit_id": exc.unit_id,
                "predicted_rul": exc.predicted_rul,
                "severity_band": exc.severity_band.value if hasattr(exc.severity_band, "value") else exc.severity_band
            },
            "severity_assessment": raw_json.get("severity_assessment", {}),
            "context": raw_json.get("context", {}),
            "recommended_action": raw_json.get("recommended_action", {}),
            "escalation": raw_json.get("escalation", {}),
            "meta": {
                "agent_mode": cfg.agent_mode,
                "agent_model": cfg.gemini_model,
                "latency_ms": latency,
                "failure_mode": "none",
                "schema_version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        }
        if isinstance(assembled["escalation"], dict) and "escalate" in assembled["escalation"]:
            assembled["escalation"]["forced_by_guardrail"] = False
            
        return TriageRecord.model_validate(assembled)
        
    try:
        # First attempt
        return attempt_call()
    except (ValidationError, ValueError) as e:
        logger.warning("Agent returned malformed JSON for %s. Retrying...", exc.exception_id)
        # FR-AGT-4 logic: 1 retry for malformed output
        try:
            return attempt_call(err_msg=repr(e))
        except (ValidationError, ValueError):
            # Still malformed
            raise ValueError("malformed_output")
    except Exception as e:
        if "Timeout" in str(e):
            raise TimeoutError("timeout")
        raise e


def process_exception(exc: ExceptionObject) -> TriageRecord:
    """Process a single exception through the triage pipeline."""
    cfg = get_config()
    start_time = time.time()
    
    record = None
    failure_mode = FailureMode.NONE
    
    # Timeout implementation wrapper
    def _execute():
        if cfg.agent_mode == AgentMode.LIVE.value:
            return run_live_triage(exc)
        else:
            return run_stub_triage(exc)
            
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute)
            record = future.result(timeout=cfg.agent.timeout_seconds)
            
    except concurrent.futures.TimeoutError:
        logger.error("Agent timed out for exception %s", exc.exception_id)
        failure_mode = FailureMode.TIMEOUT
    except ValueError as ve:
        if str(ve) == "malformed_output":
            logger.error("Agent returned malformed output twice for %s", exc.exception_id)
            failure_mode = FailureMode.MALFORMED_OUTPUT
        else:
            logger.error("Agent tool/logic error for exception %s: %s", exc.exception_id, ve)
            failure_mode = FailureMode.TOOL_ERROR
    except Exception as e:
        logger.error("Agent failed for exception %s: %r", exc.exception_id, e)
        failure_mode = FailureMode.TOOL_ERROR
        
    latency_ms = int((time.time() - start_time) * 1000)
    
    if record is None or failure_mode != FailureMode.NONE:
        # Agent crashed or failed
        record = create_failsafe_record(
            exception_id=exc.exception_id,
            run_id=exc.run_id,
            unit_id=exc.unit_id,
            predicted_rul=exc.predicted_rul,
            severity_band=exc.severity_band,
            failure_mode=failure_mode,
            latency_ms=latency_ms,
            agent_mode=cfg.agent_mode,
            agent_model=cfg.gemini_model
        )
    else:
        # Inject latency meta
        record.meta.latency_ms = latency_ms
        
    # Apply deterministic guardrails (FR-GRD-1, FR-GRD-2)
    record = apply_guardrails(record)
    
    return record
