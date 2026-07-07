"""SustainAI FastAPI Service.

Boundary: exposes the operational pipeline via REST endpoints.
Implements TRD Section 11 (Priority 5 fixes).
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from sustainai.config import DATA_DIR, OUTPUTS_DIR, MODELS_DIR, get_config
from sustainai.schemas import (
    ErrorResponse,
    HealthResponse,
    QueueSummary,
    RunResponse,
    Split,
    TriageRecord,
    ExceptionObject
)

from sustainai.predict import run_predictions
from sustainai.exceptions import generate_exceptions
from sustainai.agent.tools import init_tools
from sustainai.agent.triage_agent import process_exception
from sustainai.reports import generate_queue_summary, write_triage_artifacts

logger = logging.getLogger(__name__)

app = FastAPI(title="SustainAI API", version="0.1.0")

# In-memory mock database
run_status: Dict[str, str] = {}


def execute_pipeline(run_id: str) -> None:
    try:
        run_status[run_id] = "running"
        cfg = get_config()
        
        predictions = run_predictions(Split.TEST, run_id)
        
        meta_path = MODELS_DIR / "threshold_report.json"
        if meta_path.exists():
            with open(meta_path, "r") as f:
                t_report = json.load(f)
                critical_max = t_report.get("tuned_critical_max", cfg.severity.critical_max)
        else:
            critical_max = cfg.severity.critical_max
            
        from sustainai.schemas import ThresholdsUsed
        thresholds = ThresholdsUsed(
            critical_max=critical_max,
            warning_max=cfg.severity.warning_max,
            watch_max=cfg.severity.watch_max
        )
        
        exceptions = generate_exceptions(predictions, thresholds)
        
        out_dir = OUTPUTS_DIR / "runs" / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Dump representations
        with open(out_dir / "predictions.json", "w") as f:
            json.dump([p.model_dump(mode="json") for p in predictions], f, indent=2)
            
        with open(out_dir / "exceptions.json", "w") as f:
            json.dump([e.model_dump(mode="json") for e in exceptions], f, indent=2)
            
        init_tools(run_id)
        triage_records = []
        for exc in exceptions:
            # Setup active context cleanly through the module API
            import sustainai.agent.tools as agent_tools
            agent_tools.set_active_unit(exc.unit_id)
            record = process_exception(exc)
            triage_records.append(record)
            
        summary = generate_queue_summary(run_id, triage_records)
        write_triage_artifacts(out_dir, triage_records, summary)
        
        run_status[run_id] = "complete"
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error("Run %s failed: %s", run_id, str(e), exc_info=True)
        run_status[run_id] = "failed"


@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    cfg = get_config()
    model_meta = {}
    try:
        with open(MODELS_DIR / "model_meta.json", "r") as f:
            model_meta = json.load(f)
    except FileNotFoundError:
        pass
        
    return HealthResponse(
        status="healthy",
        model_id=model_meta.get("model_id", "none"),
        agent_mode=cfg.agent_mode,
        schema_version="1.0"
    )


@app.post("/runs", status_code=202)
def trigger_run(background_tasks: BackgroundTasks) -> dict:
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    run_status[run_id] = "pending"
    background_tasks.add_task(execute_pipeline, run_id)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def get_status(run_id: str) -> dict[str, Any]:
    status = run_status.get(run_id)
    summary_path = OUTPUTS_DIR / "runs" / run_id / "run_summary.json"
    
    if not status:
        if summary_path.exists():
            status = "complete"
        else:
            raise HTTPException(status_code=404, detail="Run not found")
            
    res = {"run_id": run_id, "status": status}
    
    if status == "complete" and summary_path.exists():
        with open(summary_path, "r") as f:
            res["queue_summary"] = json.load(f)
            
    return res


@app.get("/runs/{run_id}/exceptions")
def get_exceptions(run_id: str) -> list[dict]:
    exc_path = OUTPUTS_DIR / "runs" / run_id / "exceptions.json"
    if not exc_path.exists():
        raise HTTPException(status_code=404, detail="Exceptions not found")
    with open(exc_path, "r") as f:
        return json.load(f)


@app.get("/exceptions/{exception_id}")
def get_triage(exception_id: str) -> dict:
    for run_path in (OUTPUTS_DIR / "runs").iterdir():
        if not run_path.is_dir(): continue
        
        # Searching triage.json first (as typically exception_id is a 1:1 mapping with triage_record here)
        triage_file = run_path / "triage.json"
        
        records = []
        if triage_file.exists():
            with open(triage_file, "r") as f:
                records = json.load(f)
                
        # Also need the exception to bundle them together
        exc_file = run_path / "exceptions.json"
        exceptions = []
        if exc_file.exists():
            with open(exc_file, "r") as f:
                exceptions = json.load(f)
                
        for exc in exceptions:
            if exc["exception_id"] == exception_id:
                # Find matching record
                tr = next((r for r in records if r["exception_id"] == exception_id), None)
                return {
                    "exception": exc,
                    "triage_record": tr
                }
                
    raise HTTPException(status_code=404, detail="Exception target not found")

@app.post("/exceptions/{exception_id}/triage")
def trigger_retriage(exception_id: str) -> dict:
    for run_path in (OUTPUTS_DIR / "runs").iterdir():
        if not run_path.is_dir(): continue
        
        exc_file = run_path / "exceptions.json"
        if not exc_file.exists(): continue
        
        with open(exc_file, "r") as f:
            exceptions = json.load(f)
            
        target_exc_dict = next((e for e in exceptions if e["exception_id"] == exception_id), None)
        if target_exc_dict:
            # We found it!
            run_id = run_path.name
            target_exc = ExceptionObject(**target_exc_dict)
            
            # Re-init tool scope (history arrays)
            init_tools(run_id)
            import sustainai.agent.tools as agent_tools
            agent_tools.set_active_unit(target_exc.unit_id)
            
            # Trigger full extraction over triage paths
            new_record = process_exception(target_exc)
            
            # Persist: Update triage.json by dropping old and inserting new
            triage_file = run_path / "triage.json"
            all_records = []
            if triage_file.exists():
                with open(triage_file, "r") as f:
                    old_raw = json.load(f)
                    
                # load all except old one
                from sustainai.schemas import TriageRecord
                for r_raw in old_raw:
                    if r_raw.get("exception_id") != exception_id:
                        all_records.append(TriageRecord(**r_raw))
                        
            all_records.append(new_record)
            
            # Update summary and save back to disk
            summary = generate_queue_summary(run_id, all_records)
            write_triage_artifacts(run_path, all_records, summary)
            
            return new_record.model_dump(mode="json")
            
    raise HTTPException(status_code=404, detail="Exception target not found")
