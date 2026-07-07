"""SustainAI feature engineering.

Boundary: consumes canonical Parquet, computes features, and emits feature matrices.
Fits parameters (scaling, sensor drop) on training units only. Transforms val/test
identically. Implements TRD Section 5.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

from sustainai.config import DATA_DIR, MODELS_DIR, get_config
from sustainai.schemas import Split

logger = logging.getLogger(__name__)

CANONICAL_DIR = DATA_DIR / "canonical"
FEATURES_DIR = DATA_DIR / "features"


class FeatureEngineer:
    """Manages feature transformation parameters and pipeline."""

    def __init__(self, rul_cap: int, window: int, drop_threshold: float, split_seed: int):
        self.rul_cap = rul_cap
        self.window = window
        self.drop_threshold = drop_threshold
        self.split_seed = split_seed

        # Fit parameters (FR-FE-4: frozen after fit)
        self.dropped_sensors: list[str] = []
        self.retained_sensors: list[str] = []
        self.scaler: MinMaxScaler | None = None
        self.feature_columns: list[str] = []
        
        self.is_fit = False

    def get_version_hash(self) -> str:
        """Hash defining the exact feature version for reproducibility."""
        state = {
            "window": self.window,
            "drop_threshold": self.drop_threshold,
            "dropped_sensors": sorted(self.dropped_sensors),
            "retained_sensors": sorted(self.retained_sensors),
            "feature_columns": sorted(self.feature_columns),
        }
        state_str = json.dumps(state, sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:8]

    def _determine_dead_sensors(self, train_df: pd.DataFrame) -> None:
        """FR-FE-1 & Priority 5.5: Identify near-constant sensors and op settings on the train set."""
        sensor_cols = [c for c in train_df.columns if c.startswith("sensor_") or c.startswith("op_setting_")]
        variances = train_df[sensor_cols].var()
        
        self.dropped_sensors = variances[variances < self.drop_threshold].index.tolist()
        self.retained_sensors = [c for c in sensor_cols if c not in self.dropped_sensors]
        
        logger.info(
            "Dropping %d near-constant features: %s",
            len(self.dropped_sensors),
            self.dropped_sensors
        )

    def _compute_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """FR-FE-2: rolling mean, std, delta + raw values."""
        grouped = df.groupby("unit_id")
        
        # Priority 5.5: op_setting are evaluated natively now so self.retained_sensors contains them. 
        cols_to_roll = self.retained_sensors
        
        # Rolling means and stds
        rolls = grouped[cols_to_roll].rolling(self.window, min_periods=1)
        r_mean = rolls.mean().reset_index(level=0, drop=True)
        r_std = rolls.std().reset_index(level=0, drop=True)
        # Handle nan in std for window=1 by filling with 0
        r_std = r_std.fillna(0)
        
        # Delta: current - value W cycles prior
        # Using shift to get value W cycles prior. If shift > size of unit, it's NaN.
        # TRD: "clipped at unit start", so if we want the delta over W cycles but we're at cycle < W, we take (current - cycle_0).
        def compute_delta(group: pd.DataFrame) -> pd.DataFrame:
            # Shift by window
            prior = group.shift(self.window)
            # Fill NaNs with the first value of the group (unit start)
            # 'bfill' gets the first value since everything is missing up to window.
            prior = prior.bfill()
            delta = group - prior
            return delta

        delta = grouped[cols_to_roll].apply(compute_delta).reset_index(level=0, drop=True)
        
        # Rename columns to avoid collisions
        r_mean = r_mean.add_suffix("_mean")
        r_std = r_std.add_suffix("_std")
        delta = delta.add_suffix("_delta")
        
        # Concat original (minus dropped), rolling features, and metadata
        meta_cols = ["unit_id", "cycle", "split"]
        if "rul" in df.columns:
            meta_cols.append("rul")
        if "true_rul_final" in df.columns:
            meta_cols.append("true_rul_final")
            
        out_df = pd.concat([df[meta_cols], df[cols_to_roll], r_mean, r_std, delta], axis=1)
        return out_df

    def fit(self, train_df: pd.DataFrame) -> None:
        """Fit parameters on the training set (FR-FE-4 leakage discipline)."""
        logger.info("Fitting feature parameters on %d training rows", len(train_df))
        self._determine_dead_sensors(train_df)
        
        features_df = self._compute_rolling_features(train_df)
        
        self.feature_columns = [
            c for c in features_df.columns 
            if c not in ["unit_id", "cycle", "rul", "true_rul_final", "split"]
        ]
        
        # FR-FE-3: min-max scaling fit on training only
        self.scaler = MinMaxScaler()
        self.scaler.fit(features_df[self.feature_columns])
        
        self.is_fit = True
        logger.info(
            "Fitted. Retained %d total feature columns. Version hash: %s",
            len(self.feature_columns),
            self.get_version_hash()
        )

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply frozen transformation to any dataframe."""
        if not self.is_fit:
            raise RuntimeError("Must fit before transform")
            
        out = self._compute_rolling_features(df)
        out[self.feature_columns] = self.scaler.transform(out[self.feature_columns])
        return out


def make_splits_and_features() -> None:
    """Entry point for the feature engineering pipeline target."""
    cfg = get_config()
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    canonical_path = CANONICAL_DIR / "fd001_canonical.parquet"
    if not canonical_path.exists():
        raise FileNotFoundError("Run ingestion first.")
        
    df = pd.read_parquet(canonical_path)
    
    train_units = df[df["split"] == Split.TRAIN.value]["unit_id"].unique()
    
    # FR-SPL-1: Split train units into train/val 80/20 by unit
    train_unit_ids, val_unit_ids = train_test_split(
        train_units, 
        test_size=cfg.split.val_fraction, 
        random_state=cfg.split.seed
    )
    
    logger.info("Train/Val split: %d units train, %d units val", len(train_unit_ids), len(val_unit_ids))
    
    # Re-assign splits in df
    df.loc[(df["split"] == Split.TRAIN.value) & (df["unit_id"].isin(val_unit_ids)), "split"] = Split.VAL.value
    
    train_df = df[df["split"] == Split.TRAIN.value].copy()
    val_df = df[df["split"] == Split.VAL.value].copy()
    
    # Priority 2.1: Robust random truncation for val_df to simulate mid-life observation
    rs = np.random.RandomState(cfg.split.seed)
    v_units = val_df["unit_id"].unique()
    val_truncated_rows = []
    
    K = 5
    for u in v_units:
        u_df_base = val_df[val_df["unit_id"] == u].copy()
        max_cycle = u_df_base["cycle"].max()
        min_trunc = min(cfg.data.rolling_window, max_cycle)
        
        for i in range(K):
            u_df = u_df_base.copy()
            # Distinct derived seed for this truncation branch based on base seed + u + branch
            derived_seed = cfg.split.seed + int(u) * 100 + i
            local_rs = np.random.RandomState(derived_seed)
            if max_cycle > min_trunc:
                trunc_cycle = local_rs.randint(min_trunc, max_cycle + 1)
            else:
                trunc_cycle = max_cycle
                
            u_df = u_df[u_df["cycle"] <= trunc_cycle].copy()
            u_df["rul"] = np.clip(max_cycle - u_df["cycle"], 0, cfg.data.rul_cap)
            u_df["unit_id"] = int(u) * 1000 + i
            val_truncated_rows.append(u_df)
        
    if val_truncated_rows:
        val_df = pd.concat(val_truncated_rows)
        
    test_df = df[df["split"] == Split.TEST.value].copy()
    
    # Feature Engineering
    fe = FeatureEngineer(
        rul_cap=cfg.data.rul_cap,
        window=cfg.data.rolling_window,
        drop_threshold=cfg.data.sensor_drop_variance_threshold,
        split_seed=cfg.split.seed,
    )
    
    fe.fit(train_df)
    
    train_feat = fe.transform(train_df)
    val_feat = fe.transform(val_df)
    test_feat = fe.transform(test_df)
    
    # Save feature matrices
    train_feat.to_parquet(FEATURES_DIR / "train.parquet", index=False)
    val_feat.to_parquet(FEATURES_DIR / "val.parquet", index=False)
    test_feat.to_parquet(FEATURES_DIR / "test.parquet", index=False)
    
    # Save the feature engineer object (for predict-time reproducibility)
    from sustainai.features import FeatureEngineer as FeReal
    fe.__class__ = FeReal
    with open(MODELS_DIR / "feature_scaler.pkl", "wb") as f:
        pickle.dump(fe, f)
        
    logger.info("Feature engineering complete.")
    logger.info("  Train: %s", train_feat.shape)
    logger.info("  Val:   %s", val_feat.shape)
    logger.info("  Test:  %s", test_feat.shape)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    make_splits_and_features()
