"""SustainAI evaluation harness.

Boundary: End-to-end evaluation of the pipeline.
Implements TRD Section 10 (FR-EVA-1 to FR-EVA-5).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
import yaml
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from sustainai.api import app
from sustainai.config import DATA_DIR, OUTPUTS_DIR, get_config
from sustainai.schemas import TriageRecord, PredictionRecord
from sustainai.harness.metrics import calculate_harness_metrics

logger = logging.getLogger(__name__)


def map_true_severity(rul: float, crit_max: int, warn_max: int, watch_max: int) -> str:
    """Map true RUL to string bands based on frozen thresholds."""
    if rul <= crit_max:
        return "critical"
    elif rul <= warn_max:
        return "warning"
    elif rul <= watch_max:
        return "watch"
    else:
        return "normal"


def run_evaluation() -> None:
    """Implement FR-EVA-1 through FR-EVA-5."""
    cfg = get_config()
    
    # Eval output path
    eval_id = f"eval-{uuid.uuid4().hex[:8]}"
    eval_dir = OUTPUTS_DIR / "eval" / eval_id
    eval_dir.mkdir(parents=True, exist_ok=True)
    
    # Save config snapshot
    with open(eval_dir / "config_snapshot.yaml", "w") as f:
        # Pydantic-like dump if it's a dataclass
        import dataclasses
        yaml.dump(dataclasses.asdict(cfg), f)
        
    client = TestClient(app)
    logger.info("Initializing Evaluation Harness (Eval ID: %s)", eval_id)
    
    # 1. Load canonical test data and thresholds
    canon = pd.read_parquet(DATA_DIR / "canonical" / "fd001_canonical.parquet")
    test_canon = canon[canon["split"] == "test"].copy()
    
    thresh_report_path = DATA_DIR / ".." / "models" / "threshold_report.json"
    if thresh_report_path.exists():
        with open(thresh_report_path, "r") as f:
            tr = json.load(f)
            crit_max = tr.get("tuned_critical_max", cfg.severity.critical_max)
    else:
        crit_max = cfg.severity.critical_max
        
    warn_max = cfg.severity.warning_max
    watch_max = cfg.severity.watch_max
    
    # 2. Ground truth mapping
    test_latest = test_canon.sort_values(["unit_id", "cycle"]).groupby("unit_id").tail(1)
    
    ground_truth = {}
    for row in test_latest.itertuples():
        true_rul = row.true_rul_final
        true_band = map_true_severity(true_rul, crit_max, warn_max, watch_max)
        ground_truth[row.unit_id] = {
            "true_rul": true_rul,
            "true_band": true_band
        }
        
    logger.info("Ground truth computed for %d test engines.", len(ground_truth))
    
    # 3. Invoke API and time it
    start_time = time.time()
    
    # Using TRD Route /runs (Fix for Priority 5)
    logger.info("Triggering API pipeline...")
    trig_resp = client.post("/runs")
    assert trig_resp.status_code == 202, "Pipeline trigger failed"
    run_id = trig_resp.json()["run_id"]
    
    logger.info("Polling for completion (%s)...", run_id)
    while True:
        st_resp = client.get(f"/runs/{run_id}")
        assert st_resp.status_code == 200
        st = st_resp.json()["status"]
        if st in ("complete", "failed"):
            break
        time.sleep(1)
        
    wall_clock_s = time.time() - start_time
    
    if st == "failed":
        raise RuntimeError("Pipeline run failed.")
        
    # 4. Gather results (using correct TRD routes)
    # The /runs/{run_id} returns status and queue_summary if complete (per Priority 5.1)
    queue_summary = st_resp.json().get("queue_summary", {})
    
    # Fetch original predictions used during this run to compute base metrics! (Priority 4.1)
    # The API doesn't expose raw predictions easily, so we can fetch them from outputs/runs/{run_id}/predictions.json
    pred_path = OUTPUTS_DIR / "runs" / run_id / "predictions.json"
    with open(pred_path, "r") as f:
        raw_predictions = json.load(f)
        
    predictions_map = {p["unit_id"]: p["predicted_rul"] for p in raw_predictions}
    
    y_true = []
    y_pred = []
    y_true_band = []
    y_pred_band = []
    
    per_engine = []
    misses = []
    false_alarms = []
    
    for uid in ground_truth.keys():
        t_rul = float(ground_truth[uid]["true_rul"])
        t_band = ground_truth[uid]["true_band"]
        p_rul = float(predictions_map.get(uid, 0.0))
        p_band = map_true_severity(p_rul, crit_max, warn_max, watch_max)
        
        y_true.append(t_rul)
        y_pred.append(p_rul)
        y_true_band.append(t_band)
        y_pred_band.append(p_band)
        
        is_true_crit = (t_rul <= crit_max)
        is_pred_crit = (p_rul <= crit_max)
        
        engine_report = {
            "unit_id": int(uid),
            "true_rul": t_rul,
            "predicted_rul": p_rul,
            "true_band": t_band,
            "predicted_band": p_band
        }
        per_engine.append(engine_report)
        
        if is_true_crit and not is_pred_crit:
            misses.append(engine_report) # false negative
        elif not is_true_crit and is_pred_crit:
            false_alarms.append(engine_report) # false positive
            
    # Compute base metrics
    base_metrics = calculate_harness_metrics(
        np.array(y_true), np.array(y_pred), 
        np.array(y_true_band), np.array(y_pred_band), 
        crit_max
    )
    
    # Agent integrity metrics
    # Fetch all triage records
    all_triage_ids = queue_summary.get("all_records_index", [])
    latencies = []
    agent_failures = 0
    triage_records = []
    
    for t_id in all_triage_ids:
        r_resp = client.get(f"/exceptions/{t_id}")
        assert r_resp.status_code == 200
        # The exception endpoint returns exception + triage_record
        data = r_resp.json()
        rec = data.get("triage_record")
        if rec:
            latencies.append(rec["meta"]["latency_ms"])
            if rec["meta"]["failure_mode"] != "none":
                agent_failures += 1
            triage_records.append(rec)
            
    total_exceptions = len(all_triage_ids)
    
    # Save output artifacts
    with open(eval_dir / "per_engine.json", "w") as f: json.dump(per_engine, f, indent=2)
    with open(eval_dir / "misses.json", "w") as f: json.dump(misses, f, indent=2)
    with open(eval_dir / "false_alarms.json", "w") as f: json.dump(false_alarms, f, indent=2)
    with open(eval_dir / "latency.json", "w") as f: json.dump(latencies, f, indent=2)
    
    # Generate Target Comparison Table
    recall = base_metrics["critical_recall"]
    precision = base_metrics["critical_precision"]
    schema_valid_pct = 1.0 - (agent_failures / total_exceptions if total_exceptions > 0 else 0.0)
    latency_pass = bool(latencies and np.percentile(latencies, 95) <= 15000)
    latency_status = "PASS (stub mode; live measurement pending AC-4)" if latency_pass else "MISS (stub mode; live measurement pending AC-4)"
    
    target_comparison = {
        "targets": {
            "critical_recall_min": 0.80,
            "critical_precision_min": 0.65,
            "agent_latency_p95_max_ms": 15000,
            "agent_schema_validity_min": 1.0
        },
        "results": {
            "critical_recall": {"value": round(recall, 3), "status": "PASS" if recall >= 0.80 else "MISS"},
            "critical_precision": {"value": round(precision, 3), "status": "PASS" if precision >= 0.65 else "MISS"},
            "agent_latency_p95_ms": {"value": int(np.percentile(latencies, 95)) if latencies else 0, "status": latency_status},
            "agent_schema_validity": {"value": round(schema_valid_pct, 2), "status": "PASS" if schema_valid_pct >= 1.0 else "MISS"}
        }
    }
    
    metrics_report = {
        "eval_id": eval_id,
        "run_id": run_id,
        "mode": cfg.agent_mode,
        "wall_clock_time_seconds": round(wall_clock_s, 2),
        "total_test_engines": len(ground_truth),
        "prediction_metrics": base_metrics,
        "agent_integrity": {
            "failure_rate": round(agent_failures / total_exceptions, 2) if total_exceptions > 0 else 0,
            "latency_p50_ms": int(np.percentile(latencies, 50)) if latencies else 0,
            "latency_p95_ms": int(np.percentile(latencies, 95)) if latencies else 0,
            "total_processed": total_exceptions
        },
        "target_comparison": target_comparison
    }
    
    with open(eval_dir / "metrics.json", "w") as f: json.dump(metrics_report, f, indent=2)
    
    logger.info("Evaluation complete! Target Directory: %s", eval_dir)
    print(f"EVAL ID: {eval_id}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_evaluation()
