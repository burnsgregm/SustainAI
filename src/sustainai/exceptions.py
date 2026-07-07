"""SustainAI exception generation.

Boundary: maps predicted RUL to severity bands and emits exception objects
for engines requiring triage. Tunes the critical threshold once.
Implements TRD Section 7.3 (FR-EXC-1 through FR-EXC-3).
"""

from __future__ import annotations

import json
import logging
import uuid
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sustainai.config import DATA_DIR, MODELS_DIR, get_config
from sustainai.schemas import ExceptionObject, PredictionRecord, SeverityBand, ThresholdsUsed

logger = logging.getLogger(__name__)


def map_severity(predicted_rul: float, thresholds: ThresholdsUsed) -> SeverityBand:
    """FR-EXC-1: Map predicted RUL to severity bands."""
    if predicted_rul <= thresholds.critical_max:
        return SeverityBand.CRITICAL
    elif predicted_rul <= thresholds.warning_max:
        return SeverityBand.WARNING
    elif predicted_rul <= thresholds.watch_max:
        return SeverityBand.WATCH
    else:
        return SeverityBand.NORMAL


def generate_exceptions(predictions: list[PredictionRecord], thresholds: ThresholdsUsed) -> list[ExceptionObject]:
    """FR-EXC-2: Emit one exception object per critical or warning engine."""
    exceptions = []
    
    for pred in predictions:
        band = map_severity(pred.predicted_rul, thresholds)
        
        # Exceptions only generated for Critical and Warning
        if band in (SeverityBand.CRITICAL, SeverityBand.WARNING):
            exc = ExceptionObject(
                exception_id=str(uuid.uuid4()),
                run_id=pred.run_id,
                unit_id=pred.unit_id,
                predicted_rul=pred.predicted_rul,
                severity_band=band,
                thresholds_used=thresholds,
                model_id=pred.model_id,
                created_at=pred.created_at
            )
            exceptions.append(exc)
            
    return exceptions


def tune_critical_threshold() -> int:
    """FR-EXC-3: Tune the critical threshold on the validation split."""
    cfg = get_config()
    default_critical = cfg.severity.critical_max
    
    logger.info("Tuning critical_max from default %d", default_critical)
    
    val_path = DATA_DIR / "features" / "val.parquet"
    import hashlib
    with open(val_path, "rb") as f:
        val_hash = hashlib.md5(f.read()).hexdigest()
    import os
    val_mtime = os.path.getmtime(val_path)
    
    from sustainai.predict import Predictor
    val_feat = pd.read_parquet(val_path)
    
    val_latest = val_feat.sort_values(["unit_id", "cycle"]).groupby("unit_id").tail(1).copy()
    y_true = val_latest["rul"].values
    
    pred_service = Predictor()
    records = pred_service.predict(val_latest, run_id="tuning")
    y_pred = np.array([r.predicted_rul for r in records])
    
    # Calculate RUL Distribution
    d_summary = {
        "min": int(np.min(y_true)),
        "max": int(np.max(y_true)),
        "q25": int(np.percentile(y_true, 25)),
        "q50": int(np.percentile(y_true, 50)),
        "q75": int(np.percentile(y_true, 75)),
        "count_at_or_below_critical25": int(np.sum(y_true <= 25)),
        "count_at_or_below_warningmax": int(np.sum(y_true <= cfg.severity.warning_max)),
    }
    
    report = {
        "val_parquet_md5": val_hash,
        "val_parquet_mtime": val_mtime,
        "true_rul_distribution": d_summary,
        "provisional_critical_max": default_critical,
    }
    
    if d_summary["count_at_or_below_critical25"] < 5:
        logger.warning(
            "Tuning set contains < 5 critical targets at %d. "
            "Refusing to revise. Falling back to %d.",
            default_critical, default_critical
        )
        report["tuned_critical_max"] = default_critical
        report["refusal_reason"] = "degenerative_tuning_sparsity"
        
        with open(MODELS_DIR / "threshold_report.json", "w") as f:
            json.dump(report, f, indent=2)
        return default_critical
    
    best_cost = float('inf')
    best_threshold = default_critical
    costs = []
    
    for cand in range(10, 51):
        y_true_crit = (y_true <= cand).astype(int)
        y_pred_crit = (y_pred <= cand).astype(int)
        
        fn = np.sum((y_true_crit == 1) & (y_pred_crit == 0))
        fp = np.sum((y_true_crit == 0) & (y_pred_crit == 1))
        
        cost = 10 * fn + 1 * fp
        costs.append({"threshold": cand, "cost": int(cost), "fn": int(fn), "fp": int(fp)})
        
        if cost < best_cost:
            best_cost = cost
            best_threshold = cand
        elif cost == best_cost:
            # On cost ties, prefer the provisional 25 over others
            if cand == default_critical:
                best_threshold = cand
            elif best_threshold != default_critical:
                # If neither is 25, just keep whichever we found earlier (default behavior)
                # Resolve cost ties by preferring the provisional value 25 explicitly over sweep limits.
                # If tied over minimum, we don't pick minimum unless it's the only one. 
                pass
                
    logger.info("Best threshold found: %d with cost %d", best_threshold, best_cost)
    
    report["tuned_critical_max"] = best_threshold
    report["tuning_results"] = costs
    report["best_cost"] = int(best_cost)
    
    with open(MODELS_DIR / "threshold_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    return best_threshold

def main() -> None:
    """Entry point for tuning the threshold after training."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    tuned_val = tune_critical_threshold()
    print(f"Tuning complete. New critical_max: {tuned_val}")

if __name__ == "__main__":
    main()
