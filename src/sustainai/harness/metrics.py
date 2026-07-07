"""SustainAI metrics math.

Boundary: pure mathematical metric computations for unit-testability.
Implements TRD Section 10.2.
"""

from __future__ import annotations

import numpy as np

def calculate_nasa_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calculate the asymmetric NASA C-MAPSS scoring function (Section 10.2)."""
    d = y_pred - y_true
    score = np.where(d < 0, np.exp(-d / 13) - 1, np.exp(d / 10) - 1)
    return float(np.sum(score))


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray, threshold: int) -> dict[str, float]:
    """Calculate regression and thresholded classification metrics."""
    score = calculate_nasa_score(y_true, y_pred)
    
    # Classification for the critical class
    y_true_crit = (y_true <= threshold).astype(int)
    y_pred_crit = (y_pred <= threshold).astype(int)
    
    tp = np.sum((y_true_crit == 1) & (y_pred_crit == 1))
    fp = np.sum((y_true_crit == 0) & (y_pred_crit == 1))
    fn = np.sum((y_true_crit == 1) & (y_pred_crit == 0))
    tn = np.sum((y_true_crit == 0) & (y_pred_crit == 0))
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    return {
        "nasa_score": float(score),
        "precision": float(precision),
        "recall": float(recall),
        "tp": int(tp),
        "fp": int(fp),
        "fn": int(fn),
        "tn": int(tn)
    }

def calculate_harness_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_true_band: np.ndarray, y_pred_band: np.ndarray, threshold: int) -> dict:
    """Metrics calculated over the 100 test units during evaluation."""
    rmse = np.sqrt(np.mean((y_pred - y_true) ** 2))
    mae = np.mean(np.abs(y_pred - y_true))
    nasa = calculate_nasa_score(y_true, y_pred)
    
    # Critical class metrics
    y_true_crit = (y_true <= threshold).astype(int)
    y_pred_crit = (y_pred <= threshold).astype(int)
    
    tp = int(np.sum((y_true_crit == 1) & (y_pred_crit == 1)))
    fp = int(np.sum((y_true_crit == 0) & (y_pred_crit == 1)))
    fn = int(np.sum((y_true_crit == 1) & (y_pred_crit == 0)))
    tn = int(np.sum((y_true_crit == 0) & (y_pred_crit == 0)))
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Band accuracy
    band_accuracy = np.mean(y_true_band == y_pred_band)
    
    return {
        "rmse": float(rmse),
        "mae": float(mae),
        "nasa_score": float(nasa),
        "band_accuracy": float(band_accuracy),
        "critical_confusion": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn
        },
        "critical_precision": float(precision),
        "critical_recall": float(recall),
        "critical_f1": float(f1)
    }
