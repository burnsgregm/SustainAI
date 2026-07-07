import pytest
from datetime import datetime, timezone
import uuid
import pandas as pd
from pathlib import Path
import json

from sustainai.schemas import ExceptionObject, SeverityBand, ThresholdsUsed, FailureMode, TriageRecord, AgentMode
from sustainai.agent.stub import run_stub_triage
from sustainai.agent.guardrails import apply_guardrails, create_failsafe_record
from sustainai.agent.tools import ToolContext, init_tools, get_fleet_summary
from sustainai.config import DATA_DIR


def create_mock_canonical_and_runs(tmp_path: Path):
    """Mock the file dependencies required by ToolContext."""
    canonical_dir = tmp_path / "data" / "canonical"
    canonical_dir.mkdir(parents=True)
    run_dir = tmp_path / "data" / "runs" / "test_run"
    run_dir.mkdir(parents=True)
    
    # Create canonical parquet
    df = pd.DataFrame({
        "unit_id": [1],
        "cycle": [1],
        "sensor_02": [10.0],
        "split": ["test"],
        "rul": [5],
        "true_rul_final": [5]
    })
    df.to_parquet(canonical_dir / "fd001_canonical.parquet")
    
    # Create predictions
    with open(run_dir / "predictions.json", "w") as f:
        json.dump([{"unit_id": 1, "predicted_rul": 10.0}], f)
        
    # We patch DATA_DIR for tests below.
    return tmp_path / "data"


# =============================================================================
# T-6: Agent outputs strictly parse into TriageRecord schema
# =============================================================================
def test_t6_stub_triage_validates_schema(monkeypatch, tmp_path):
    """T-6: Ensure the stub output validates perfectly."""
    data_dir = create_mock_canonical_and_runs(tmp_path)
    monkeypatch.setattr("sustainai.agent.tools.DATA_DIR", data_dir)
    
    init_tools("test_run")
    
    exc = ExceptionObject(
        exception_id="exc123",
        run_id="test_run",
        unit_id=1,
        predicted_rul=5.0,
        severity_band=SeverityBand.CRITICAL,
        thresholds_used=ThresholdsUsed(critical_max=25, warning_max=50, watch_max=75),
        model_id="m1",
        created_at=datetime.now(timezone.utc)
    )
    
    record = run_stub_triage(exc)
    
    # Model dumping asserts validation holds
    dumped = record.model_dump(mode="json")
    assert dumped["engine"]["severity_band"] == "critical"


# =============================================================================
# T-7: Guardrail forces escalation if agent fails
# =============================================================================
def test_t7_guardrail_failure_mode():
    """T-7: Guardrail properly forces escalation if agent fails."""
    record = create_failsafe_record(
        exception_id="e1", run_id="r1", unit_id=1, predicted_rul=10.0,
        severity_band=SeverityBand.CRITICAL, failure_mode=FailureMode.TIMEOUT,
        latency_ms=10, agent_mode=AgentMode.LIVE.value, agent_model="model"
    )
    
    # Assume it didn't escalate for some bizarre reason (failsafe already escalates, but test apply_guardrails)
    record.escalation.escalate = False
    
    guarded = apply_guardrails(record)
    assert guarded.escalation.escalate is True
    assert guarded.escalation.forced_by_guardrail is True


# =============================================================================
# T-8: Guardrail forces escalation on AI crashes (Timeout/Malformed)
# =============================================================================
def test_t8_failsafes_on_agent_failure(monkeypatch):
    """T-8: Verify process_exception yields failsafe TriageRecord on LLM crash/timeout."""
    import time
    from sustainai.agent.triage_agent import process_exception
    from sustainai.config import SustainAIConfig
    
    # Mock config to live mode to trigger failure loops
    def mock_cfg():
        cfg = SustainAIConfig()
        cfg.agent_mode = "live"
        cfg.agent.timeout_seconds = 1  # 1 sec timeout
        return cfg
    
    monkeypatch.setattr("sustainai.agent.triage_agent.get_config", mock_cfg)
    
    # Base Exception
    exc = ExceptionObject(
        exception_id="timeout_test",
        run_id="test_run",
        unit_id=1,
        predicted_rul=10.0,
        severity_band=SeverityBand.CRITICAL,
        thresholds_used=ThresholdsUsed(critical_max=25, warning_max=50, watch_max=75),
        model_id="m1",
        created_at=datetime.now(timezone.utc)
    )
    
    # Case 1: Timeout execution
    def mock_sleep_vertex(*args, **kwargs):
        time.sleep(2)  # exceed 1s limit
        
    monkeypatch.setattr("sustainai.agent.triage_agent._call_vertex_ai", mock_sleep_vertex)
    record1 = process_exception(exc)
    assert record1.meta.failure_mode == FailureMode.TIMEOUT
    assert record1.escalation.escalate is True
    assert record1.escalation.forced_by_guardrail is True
    
    # Case 2: Malformed Output Loop
    def mock_malformed(*args, **kwargs):
        raise ValueError("malformed_output")
        
    monkeypatch.setattr("sustainai.agent.triage_agent._call_vertex_ai", mock_malformed)
    record2 = process_exception(exc)
    assert record2.meta.failure_mode == FailureMode.MALFORMED_OUTPUT
    assert record2.escalation.escalate is True
    assert record2.escalation.forced_by_guardrail is True
    

# =============================================================================
# T-13: Vertex Response Parsing and Contract Integrity
# =============================================================================
def test_t13_vertex_response_parsing(monkeypatch):
    from sustainai.agent.triage_agent import run_live_triage
    from sustainai.config import SustainAIConfig
    import types
    import json
    
    def mock_cfg():
        cfg = SustainAIConfig()
        cfg.agent_mode = "live"
        return cfg
    monkeypatch.setattr("sustainai.agent.triage_agent.get_config", mock_cfg)
    
    exc = ExceptionObject(
        exception_id="test_parse",
        run_id="test_run",
        unit_id=1,
        predicted_rul=5.0,
        severity_band=SeverityBand.CRITICAL,
        thresholds_used=ThresholdsUsed(critical_max=25, warning_max=50, watch_max=75),
        model_id="m1",
        created_at=datetime.now(timezone.utc)
    )
    
    # 1. Well-formed JSON text test (Model outputs only 4 blocks now)
    valid_record_dict = {
        "severity_assessment": {"agrees_with_band": True, "assessed_band": "critical", "reasoning": "high risk"},
        "context": {
            "sensor_trend_summary": "none",
            "degradation_summary": "none",
            "fleet_position": "none",
            "tool_calls_made": 0
        },
        "recommended_action": {
            "action_type": "schedule_inspection",
            "horizon_cycles": 10,
            "details": "none"
        },
        "escalation": {"escalate": True, "rationale": "critical"}
    }
    
    class MockPart:
        def __init__(self, text):
            self.text = text
    class MockContent:
        def __init__(self, text):
            self.parts = [MockPart(text)]
    class MockCandidate:
        def __init__(self, text):
            self.content = MockContent(text)
    class MockResponse:
        def __init__(self, text):
            self.candidates = [MockCandidate(text)]
            
    call_count = 0
            
    class MockGenerativeModel:
        def __init__(self, model_name):
            pass
        def generate_content(self, prompt, generation_config=None):
            nonlocal call_count
            call_count += 1
            if "INVALID_RESPONSE" in prompt:
                # Return empty or bad text
                return MockResponse("{bad_json")
            return MockResponse(json.dumps(valid_record_dict))
            
    # Mock vertexai module to prevent import errors if not installed in stub environment
    mock_vertexai = types.ModuleType("vertexai")
    mock_vertexai.generative_models = types.ModuleType("generative_models")
    mock_vertexai.generative_models.GenerativeModel = MockGenerativeModel
    import sys
    sys.modules["vertexai"] = mock_vertexai
    sys.modules["vertexai.generative_models"] = mock_vertexai.generative_models

    # Test valid
    rec = run_live_triage(exc)
    assert rec.engine.severity_band == "critical"
    
    # Test invalid routes to malformed logic, raises ValueError("malformed_output")
    call_count = 0
    exc.exception_id = "INVALID_RESPONSE" # Pass signal via ID to mock
    monkeypatch.setattr("sustainai.agent.triage_agent.SYSTEM_PROMPT", "{exception_id}") # Make prompt the ID
    try:
        run_live_triage(exc)
        assert False, "Should raise malformed_output"
    except ValueError as e:
        assert str(e) == "malformed_output"
    # Call count should be 2 because run_live_triage retries once
    assert call_count == 2

# =============================================================================
# T-9: Tools cannot access label fields
# =============================================================================
def test_t9_tool_context_label_isolation(monkeypatch, tmp_path):
    """T-9: Tools cannot access label fields within loaded data."""
    data_dir = create_mock_canonical_and_runs(tmp_path)
    monkeypatch.setattr("sustainai.agent.tools.DATA_DIR", data_dir)
    
    ctx = ToolContext("test_run")
    df = ctx.test_canon
    
    # Assert labels are absent (T-9)
    assert "rul" not in df.columns
    assert "true_rul" not in df.columns
    assert "true_rul_final" not in df.columns
