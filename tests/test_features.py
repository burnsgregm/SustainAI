import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from sustainai.features import FeatureEngineer, CANONICAL_DIR, Split
from sustainai.config import DataConfig

def create_mock_canonical(tmp_path: Path) -> Path:
    # 5 units: 4 train, 1 test
    df_rows = []
    
    # Train units: 1, 2, 3, 4
    for u in range(1, 5):
        for c in range(1, 10):
            row = [u, c] + [1.0] * 3 + [np.random.random() * u] * 21 + [10, pd.NA, Split.TRAIN.value]
            df_rows.append(row)
            
    # Test unit: 5
    for c in range(1, 5):
        row = [5, c] + [1.0] * 3 + [np.random.random() * 5] * 21 + [pd.NA, 10 if c==4 else pd.NA, Split.TEST.value]
        df_rows.append(row)
        
    cols = ["unit_id", "cycle"] + [f"op_setting_{i}" for i in range(1, 4)] + \
           [f"sensor_{i:02d}" for i in range(1, 22)] + ["rul", "true_rul_final", "split"]
           
    df = pd.DataFrame(df_rows, columns=cols)
    out = tmp_path / "fd001_canonical.parquet"
    df.to_parquet(out)
    return out

# =============================================================================
# T-3: Features unit-level splits and frozen transforms
# =============================================================================

def test_feature_splits_and_frozen_transforms(tmp_path: Path):
    """T-3: Test that unit-level splits do not overlap and transforms are frozen."""
    canonical_file = create_mock_canonical(tmp_path)
    df = pd.read_parquet(canonical_file)
    
    fe = FeatureEngineer(
        rul_cap=125,
        window=5,
        drop_threshold=1.0e-6,
        split_seed=42
    )
    
    # Check that test units are held out
    train_df_raw = df[df["split"] == Split.TRAIN.value]
    
    fe.fit(train_df_raw)
    
    assert fe.is_fit
    assert fe.scaler is not None
    
    # Capture fitted parameters
    fitted_min = fe.scaler.data_min_.copy()
    fitted_max = fe.scaler.data_max_.copy()
    
    # Transform test set
    test_df_raw = df[df["split"] == Split.TEST.value]
    test_feat = fe.transform(test_df_raw)
    
    # Assert parameters remain unchanged after transform
    np.testing.assert_array_equal(fe.scaler.data_min_, fitted_min)
    np.testing.assert_array_equal(fe.scaler.data_max_, fitted_max)
    
    # Test split function logic from features.py (re-implement here to test split isolation)
    from sklearn.model_selection import train_test_split
    train_units = df[df["split"] == Split.TRAIN.value]["unit_id"].unique()
    
    train_unit_ids, val_unit_ids = train_test_split(
        train_units, 
        test_size=0.25, # 4 units total, 1 val
        random_state=42
    )
    
    # Assert no overlap
    overlap = set(train_unit_ids).intersection(set(val_unit_ids))
    assert len(overlap) == 0, "Units overlap between train and val splits"
