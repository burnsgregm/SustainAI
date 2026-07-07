import pytest
import numpy as np
from sustainai.harness.metrics import calculate_harness_metrics, calculate_nasa_score

def test_t10_metric_math():
    """T-10: Synthetic metric math verification per TRD Section 12."""
    # 10 synthetic sets matching bounds perfectly
    # critical_max = 20
    # Expected inputs
    y_true = np.array([5,   15, 25, 100, 10,  22, 19, 50, 4, 18])
    y_pred = np.array([4,   18, 22, 90,  15,  26, 17, 30, 2, 22])
    # Truth bands based on thresholds: C=<=20, W<=40
    y_true_band = np.array(
        ["critical", "critical", "warning", "normal", "critical", 
         "warning", "critical", "normal", "critical", "critical"]
    )
    y_pred_band = np.array(
        ["critical", "critical", "warning", "normal", "critical", 
         "warning", "critical", "warning", "critical", "warning"]
    )
    
    metrics = calculate_harness_metrics(
        y_true, y_pred, y_true_band, y_pred_band, threshold=20
    )
    
    # Hand-calculate expected RMSE
    # Diff: -1, 3, -3, -10, 5, 4, -2, -20, -2, 4
    # Sq:   1, 9, 9, 100, 25, 16, 4, 400, 4, 16 -> Sum = 584 / 10 = 58.4
    expected_rmse = np.sqrt(58.4)
    assert np.isclose(metrics["rmse"], expected_rmse)
    
    # Hand-calculate expected MAE
    # Abs: 1, 3, 3, 10, 5, 4, 2, 20, 2, 4 -> Sum = 54 / 10 = 5.4
    assert np.isclose(metrics["mae"], 5.4)
    
    # Hand-calculate Critical metrics:
    # true critical indices (<=20): 0, 1, 4, 6, 8, 9 (count = 6)
    # pred critical indices (<=20): 0, 1, 4, 6, 8 (count = 5)
    # TP = idx matched: 0, 1, 4, 6, 8 -> 5
    # FN = true crit but not pred (idx 9) -> 1
    # FP = pred crit but not true (none) -> 0
    # TN = neither -> 4
    assert metrics["critical_confusion"]["tp"] == 5
    assert metrics["critical_confusion"]["fn"] == 1
    assert metrics["critical_confusion"]["fp"] == 0
    assert metrics["critical_confusion"]["tn"] == 4
    
    # Precision = 5 / (5+0) = 1.0
    # Recall = 5 / (5+1) = 5/6 = 0.8333
    assert np.isclose(metrics["critical_precision"], 1.0)
    assert np.isclose(metrics["critical_recall"], 5/6)
    
    # F1 = 2 * (1.0 * (5/6)) / (1.0 + (5/6)) = 2 * (5/6) / (11/6) = 10/11
    assert np.isclose(metrics["critical_f1"], 10/11)
    
    # Handcalc NASA Score
    # Diff (pred - true) < 0 -> e^(-d/13) - 1
    # Diff >= 0 -> e^(d/10) - 1
    # -1: e^(1/13)-1 + 3: e^(3/10)-1 + -3: e^(3/13)-1 + -10: e^(10/13)-1
    # + 5: e^(5/10)-1 + 4: e^(4/10)-1 + -2: e^(2/13)-1 + -20: e^(20/13)-1
    # -2: e^(2/13)-1 + 4: e^(4/10)-1
    
    d = y_pred - y_true
    expected_nasa = np.sum(np.where(d < 0, np.exp(-d/13) - 1, np.exp(d/10) - 1))
    assert np.isclose(metrics["nasa_score"], expected_nasa)
    
    # Band accuracy
    # matches: indices 0(C), 1(C), 2(W), 3(N), 4(C), 5(W), 6(C), 8(C) -> 8 matches
    # mismatches: 7(N!=W), 9(C!=W)
    assert np.isclose(metrics["band_accuracy"], 0.8)
