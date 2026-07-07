import pytest
from datetime import datetime, timezone
import uuid
import pandas as pd

from sustainai.schemas import ThresholdsUsed, PredictionRecord, SeverityBand
from sustainai.exceptions import map_severity, generate_exceptions

# =============================================================================
# T-4: Thresholding maps band boundaries exactly
# =============================================================================

def test_map_severity_boundaries():
    """T-4: Test values at, just below, and just above each threshold."""
    thresholds = ThresholdsUsed(critical_max=25, warning_max=60, watch_max=100)
    
    # Critical boundaries
    assert map_severity(24.9, thresholds) == SeverityBand.CRITICAL
    assert map_severity(25.0, thresholds) == SeverityBand.CRITICAL
    assert map_severity(25.1, thresholds) == SeverityBand.WARNING
    
    # Warning boundaries
    assert map_severity(59.9, thresholds) == SeverityBand.WARNING
    assert map_severity(60.0, thresholds) == SeverityBand.WARNING
    assert map_severity(60.1, thresholds) == SeverityBand.WATCH
    
    # Watch boundaries
    assert map_severity(99.9, thresholds) == SeverityBand.WATCH
    assert map_severity(100.0, thresholds) == SeverityBand.WATCH
    assert map_severity(100.1, thresholds) == SeverityBand.NORMAL


# =============================================================================
# T-5: Exception generation emits exceptions only for critical/warning
# =============================================================================

def test_generate_exceptions_filters_correctly():
    """T-5: Exception generation emits exceptions only for critical and warning."""
    thresholds = ThresholdsUsed(critical_max=25, warning_max=60, watch_max=100)
    
    now = datetime.now(timezone.utc)
    # Create 4 predictions crossing all bands
    preds = [
        PredictionRecord(unit_id=1, cycle=100, predicted_rul=10.0, model_id="m1", feature_version="v1", run_id="r1", created_at=now), # Critical
        PredictionRecord(unit_id=2, cycle=100, predicted_rul=40.0, model_id="m1", feature_version="v1", run_id="r1", created_at=now), # Warning
        PredictionRecord(unit_id=3, cycle=100, predicted_rul=80.0, model_id="m1", feature_version="v1", run_id="r1", created_at=now), # Watch
        PredictionRecord(unit_id=4, cycle=100, predicted_rul=120.0, model_id="m1", feature_version="v1", run_id="r1", created_at=now),# Normal
    ]
    
    exc = generate_exceptions(preds, thresholds)
    
    assert len(exc) == 2, "Should only generate 2 exceptions"
    assert exc[0].unit_id == 1
    assert exc[0].severity_band == SeverityBand.CRITICAL
    assert exc[1].unit_id == 2
    assert exc[1].severity_band == SeverityBand.WARNING
