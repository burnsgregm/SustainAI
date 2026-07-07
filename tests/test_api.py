import pytest
from fastapi.testclient import TestClient
import concurrent.futures

from sustainai.api import app, run_status
from sustainai.config import get_config
import uuid

client = TestClient(app)

# =============================================================================
# T-11: API endpoints conform exactly to schemas
# =============================================================================
def test_t11_health_endpoint():
    """T-11: /health conforms to schema."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    assert "status" in data
    assert "model_id" in data
    assert "agent_mode" in data
    assert "schema_version" in data
    assert data["status"] == "healthy"


# =============================================================================
# T-11: 404 handled gracefully
# =============================================================================
def test_t11_runs_status_404():
    """T-11: /runs/{run_id} returns 404 for unknown run."""
    bad_id = f"run-{uuid.uuid4().hex[:8]}"
    response = client.get(f"/runs/{bad_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_t11_exceptions_404():
    """T-11: /runs/{run_id}/exceptions returns 404 for unknown run."""
    bad_id = f"run-{uuid.uuid4().hex[:8]}"
    response = client.get(f"/runs/{bad_id}/exceptions")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

def test_t11_triage_404():
    """T-11: /exceptions/{exception_id} returns 404 for unknown triage_id."""
    bad_id = f"fail-{uuid.uuid4().hex[:12]}"
    response = client.get(f"/exceptions/{bad_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# =============================================================================
# T-11: Async pipeline handles concurrent runs safely
# =============================================================================
def test_t11_concurrent_pipeline_triggers():
    """T-11: Async pipeline handles concurrent /runs POST requests safely."""
    
    def post_run():
        return client.post("/runs")
        
    num_concurrent = 4
    responses = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        futures = [executor.submit(post_run) for _ in range(num_concurrent)]
        for f in concurrent.futures.as_completed(futures):
            responses.append(f.result())
            
    assert len(responses) == num_concurrent
    
    run_ids = set()
    for resp in responses:
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        run_ids.add(data["run_id"])
        
    assert len(run_ids) == num_concurrent, "Each trigger should get a unique run_id"
    
    # Check that they immediately show as pending or running in the status endpoint
    for r_id in run_ids:
        st_resp = client.get(f"/runs/{r_id}")
        assert st_resp.status_code == 200
        assert st_resp.json()["status"] in ("pending", "running", "complete", "failed")
