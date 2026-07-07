"""SustainAI agent tools.

Boundary: read-only access to current run artifacts. No label access.
Implements TRD Section 8.2 (FR-AGT-2, FR-AGT-3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sustainai.config import DATA_DIR, OUTPUTS_DIR, get_config
from sustainai.schemas import (
    BandCounts,
    DegradationHistory,
    FleetSummary,
    SensorTrendPoint,
    SensorTrends,
    SeverityBand,
)

# Global context for tools during a run
class ToolContext:
    def __init__(self, run_id: str):
        self.run_id = run_id
        
        # Load canonical test data (without labels)
        canonical_path = DATA_DIR / "canonical" / "fd001_canonical.parquet"
        canon = pd.read_parquet(canonical_path)
        self.test_canon = canon[canon["split"] == "test"].copy()
        
        # T-9 enforcement: ensure no labels exist in tool-visible data
        for label_col in ["rul", "true_rul", "true_rul_final"]:
            if label_col in self.test_canon.columns:
                self.test_canon = self.test_canon.drop(columns=[label_col])
                
        # Load exceptions (for fleet summary)
        exceptions_path = OUTPUTS_DIR / "runs" / run_id / "exceptions.json"
        if exceptions_path.exists():
            with open(exceptions_path, "r") as f:
                self.exceptions = json.load(f)
        else:
            self.exceptions = []
            
        # Load predictions (for fleet summary & degradation history)
        preds_path = OUTPUTS_DIR / "runs" / run_id / "predictions.json"
        if preds_path.exists():
            with open(preds_path, "r") as f:
                self.predictions = json.load(f)
        else:
            self.predictions = []
            
    def get_unit_data(self, unit_id: int) -> pd.DataFrame:
        """Get safe, label-free raw sensor data for a unit."""
        return self.test_canon[self.test_canon["unit_id"] == unit_id].sort_values("cycle")
        
    def get_unit_predictions(self, unit_id: int) -> list[dict]:
        """In a real system this would be full trajectory. Here we just have latest predict from our batch."""
        return [p for p in self.predictions if p["unit_id"] == unit_id]

# Singleton instance initialized per-run
_context: ToolContext | None = None

def set_active_unit(unit_id: int) -> None:
    """Set the active unit for tools that depend on single-engine context."""
    global _context
    if _context is not None:
        _context.active_unit_id = unit_id

def init_tools(run_id: str) -> None:
    """Initialize the tool context for a run."""
    global _context
    _context = ToolContext(run_id)

def get_sensor_trends(unit_id: int, last_n_cycles: int = 50) -> SensorTrends:
    """Return recent-cycle trajectories for informative sensors."""
    if _context is None:
        raise RuntimeError("Tools not initialized")
        
    df = _context.get_unit_data(unit_id)
    if df.empty:
        return SensorTrends(unit_id=unit_id, last_n_cycles=last_n_cycles, trends=[])
        
    # Get informative sensors (by dropping the known dead ones stored in decisions.md)
    # Using columns that start with sensor_
    sensor_cols = [c for c in df.columns if c.startswith("sensor_")]
    
    trends = []
    
    for col in sensor_cols:
        # Very simple baseline calculation (first 20 cycles)
        baseline = df[col].head(20).mean()
        
        recent = df[col].tail(last_n_cycles)
        
        # If variance is 0, it's a dead sensor, skip returning it to save tokens
        if recent.var() < 1e-6 and baseline == recent.iloc[0]:
            continue
            
        # Downsample to <= 25 points for context window efficiency
        downsample_factor = max(1, len(recent) // 25)
        points = recent.iloc[::downsample_factor].tolist()
        
        # Determine direction
        if len(recent) > 1:
            slope = np.polyfit(np.arange(len(recent)), recent.values, 1)[0]
            if slope > 0.01:
                direction = "increasing"
            elif slope < -0.01:
                direction = "decreasing"
            else:
                direction = "stable"
        else:
            direction = "stable"
            
        rate_vs_baseline = (recent.mean() / baseline) if baseline != 0 else 1.0
        if pd.isna(rate_vs_baseline) or np.isinf(rate_vs_baseline):
            rate_vs_baseline = 1.0
            
        trends.append(SensorTrendPoint(
            sensor_name=col,
            recent_values=[round(p, 4) for p in points],
            direction=direction,
            rate_vs_baseline=float(rate_vs_baseline)
        ))
        
    return SensorTrends(
        unit_id=unit_id,
        last_n_cycles=last_n_cycles,
        trends=trends
    )


def get_degradation_history(unit_id: int) -> DegradationHistory:
    """Return the predicted-RUL trajectory over the engine's observed life."""
    if _context is None:
        raise RuntimeError("Tools not initialized")
        
    df = _context.get_unit_data(unit_id)
    cycles_observed = int(df["cycle"].max()) if not df.empty else 0
    
    preds = _context.get_unit_predictions(unit_id)
    current_rul = float(preds[0]["predicted_rul"]) if preds else 0.0
    
    # In this simplified demo build, our prediction step only predicts the final cycle. 
    # To return a history without regenerating, we just return the final prediction.
    # In a full system, you would predict all cycles and return the array.
    rul_trajectory = [current_rul]
    
    return DegradationHistory(
        unit_id=unit_id,
        cycles_observed=cycles_observed,
        current_predicted_rul=current_rul,
        rul_trajectory=rul_trajectory
    )


def get_fleet_summary() -> FleetSummary:
    """Return where this engine sits relative to the fleet."""
    if _context is None:
        raise RuntimeError("Tools not initialized")
        
    cfg = get_config()
    
    preds = _context.predictions
    total = len(preds)
    
    crit_count = 0
    warn_count = 0
    watch_count = 0
    norm_count = 0
    
    for p in preds:
        r = p["predicted_rul"]
        if r <= cfg.severity.critical_max:
            crit_count += 1
        elif r <= cfg.severity.warning_max:
            warn_count += 1
        elif r <= cfg.severity.watch_max:
            watch_count += 1
        else:
            norm_count += 1
            
    counts = BandCounts(
        critical=crit_count,
        warning=warn_count,
        watch=watch_count,
        normal=norm_count
    )
    
    unit_pct = 0.0
    if hasattr(_context, 'active_unit_id') and total > 0:
        active_rul = next((p["predicted_rul"] for p in preds if p["unit_id"] == _context.active_unit_id), None)
        if active_rul is not None:
            worse_count = sum(1 for p in preds if p["predicted_rul"] < active_rul)
            unit_pct = (worse_count / total) * 100.0
            
    return FleetSummary(
        counts_by_band=counts,
        unit_percentile=float(unit_pct),
        total_units=total
    )


def get_agent_tools() -> list[dict[str, Any]]:
    """Return JSON schema definitions for the tools."""
    return [
        {
            "name": "get_sensor_trends",
            "description": "Return recent-cycle trajectories for informative sensors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "integer"},
                    "last_n_cycles": {"type": "integer", "default": 50}
                },
                "required": ["unit_id"]
            }
        },
        {
            "name": "get_degradation_history",
            "description": "Return the predicted-RUL trajectory over the engine's observed life.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_id": {"type": "integer"}
                },
                "required": ["unit_id"]
            }
        },
        {
            "name": "get_fleet_summary",
            "description": "Return counts by severity band for the current run and this unit's predicted percentile within the fleet.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ]
