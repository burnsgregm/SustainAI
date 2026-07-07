import numpy as np
import pytest
from sustainai.train import calculate_nasa_score, calculate_metrics

def test_calculate_nasa_score():
    """Verify asymmetric NASA scoring function."""
    y_true = np.array([100.0, 100.0])
    y_pred_early = np.array([90.0, 100.0])  # one is early by 10 (d = -10)
    y_pred_late = np.array([110.0, 100.0])  # one is late by 10 (d = +10)
    
    score_early = calculate_nasa_score(y_true, y_pred_early)
    score_late = calculate_nasa_score(y_true, y_pred_late)
    
    # NASA score formula:
    # d = pred - true
    # d < 0 => exp(-d/13) - 1 => exp(10/13) - 1 = exp(0.769) - 1 = 2.158 - 1 = 1.158
    # d > 0 => exp(d/10) - 1 => exp(10/10) - 1 = exp(1) - 1 = 1.718
    # Both sets include one perfect prediction (d=0) => 0
    assert score_late > score_early, "Late predictions should be penalized more than early ones"
    
def test_calculate_metrics():
    """Verify classification metrics calculation."""
    y_true = np.array([10, 20, 30, 40])
    y_pred = np.array([15, 30, 20, 45])
    threshold = 25
    
    # Critical class: <= 25.
    # True critical: [10, 20] => indices 0, 1
    # True normal: [30, 40] => indices 2, 3
    # Pred critical: [15, 20] => indices 0, 2
    # Pred normal: [30, 45] => indices 1, 3
    
    # TP: 10 (idx 0)
    # FP: 30 predicted 20 (idx 2)
    # FN: 20 predicted 30 (idx 1)
    # TN: 40 predicted 45 (idx 3)
    
    metrics = calculate_metrics(y_true, y_pred, threshold)
    
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["tn"] == 1
    
    assert metrics["precision"] == 0.5  # tp / (tp + fp) = 1 / 2
    assert metrics["recall"] == 0.5  # tp / (tp + fn) = 1 / 2
