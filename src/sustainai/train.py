"""SustainAI model training and selection.

Boundary: trains baseline and champion candidate on engineered features.
Selects the model based on validation metrics (FR-MOD-3). Serializes the
chosen model (FR-MOD-4).
"""

from __future__ import annotations

import json
import logging
import joblib
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor

from sustainai.config import DATA_DIR, MODELS_DIR, get_config
from sustainai.features import FeatureEngineer

logger = logging.getLogger(__name__)

FEATURES_DIR = DATA_DIR / "features"


from sustainai.harness.metrics import calculate_nasa_score, calculate_metrics


def train_baseline(X_train: np.ndarray, y_train: np.ndarray, seed: int) -> HistGradientBoostingRegressor:
    """FR-MOD-1: Gradient boosting baseline."""
    logger.info("Training HistGradientBoostingRegressor baseline...")
    # Light tuning: standard defaults are usually very robust for HGBR
    model = HistGradientBoostingRegressor(
        max_iter=150,
        learning_rate=0.05,
        max_depth=7,
        l2_regularization=0.1,
        random_state=seed,
    )
    model.fit(X_train, y_train)
    return model


def train_champion(
    X_train: np.ndarray, y_train: np.ndarray, 
    X_val: np.ndarray, y_val: np.ndarray, 
    seed: int
) -> MLPRegressor:
    """FR-MOD-2 (Fallback): Scikit-Learn MLP champion candidate."""
    logger.info("Training MLPRegressor champion candidate (Fallback)...")
    
    model = MLPRegressor(
        hidden_layer_sizes=(64, 32),
        alpha=0.01,
        early_stopping=True,
        validation_fraction=0.2, # validation split internally
        random_state=seed,
        max_iter=150,
        learning_rate_init=0.002
    )
    
    # MLPRegressor fits directly
    model.fit(X_train, y_train)
    
    return model


def train_and_select() -> None:
    """Entry point for FR-MOD-3 selection logic."""
    cfg = get_config()
    target_threshold = cfg.severity.critical_max
    
    logger.info("Loading feature matrices...")
    train_df = pd.read_parquet(FEATURES_DIR / "train.parquet")
    val_df = pd.read_parquet(FEATURES_DIR / "val.parquet")
    
    with open(MODELS_DIR / "feature_scaler.pkl", "rb") as f:
        fe: FeatureEngineer = pickle.load(f)
        
    feature_cols = fe.feature_columns
    
    X_train = train_df[feature_cols].values
    y_train = train_df["rul"].values
    
    # Validation occurs only at the last cycle of each validation unit to simulate real life
    # The evaluation harness measures on "held-out test engines at their latest observed cycle".
    # For fair model selection, we should evaluate metrics on the *last* cycle of each validation unit.
    val_last_cycle = val_df.groupby("unit_id").tail(1)
    X_val_last = val_last_cycle[feature_cols].values
    y_val_last = val_last_cycle["rul"].values
    
    # Train
    baseline = train_baseline(X_train, y_train, cfg.seed)
    
    # Priority 2.2: Pass validation set for early stopping
    X_val = val_df[feature_cols].values
    y_val = val_df["rul"].values
    champion = train_champion(X_train, y_train, X_val, y_val, cfg.seed)
    
    # Predict on validation last cycles
    base_pred = baseline.predict(X_val_last)
    champ_pred = champion.predict(X_val_last)
    
    # Cap predictions (FR-PRD-2 logic applied natively for clean metric evaluation)
    base_pred = np.clip(base_pred, 0, cfg.data.rul_cap)
    champ_pred = np.clip(champ_pred, 0, cfg.data.rul_cap)
    
    base_metrics = calculate_metrics(y_val_last, base_pred, target_threshold)
    champ_metrics = calculate_metrics(y_val_last, champ_pred, target_threshold)
    
    logger.info("Baseline validation metrics: %s", base_metrics)
    logger.info("Champion validation metrics: %s", champ_metrics)
    
    # FR-MOD-3 Selection Rule:
    # "champion ships only if it beats baseline on val critical-class recall 
    # at equal-or-better precision, and no worse NASA score"
    select_champion = False
    
    recall_beats = champ_metrics["recall"] > base_metrics["recall"]
    precision_eq_beat = champ_metrics["precision"] >= base_metrics["precision"]
    nasa_no_worse = champ_metrics["nasa_score"] <= base_metrics["nasa_score"]
    
    if recall_beats and precision_eq_beat and nasa_no_worse:
        select_champion = True
        logger.info("Champion elected.")
    else:
        logger.info("Baseline elected.")
    
    selected_model_id = "champion_mlp_v1" if select_champion else "baseline_hgbr_v1"
    
    # Serialize the selected model (FR-MOD-4)
    if select_champion:
        logger.info("Saving champion (Scikit-Learn MLP) model")
        model_type = "sklearn"
        model_file = "champion.pkl"
        model_path = MODELS_DIR / model_file
        joblib.dump(champion, model_path)
    else:
        logger.info("Baseline selected over champion.")
        model_type = "sklearn"
        model_file = "baseline.pkl"
        model_path = MODELS_DIR / model_file
        joblib.dump(baseline, model_path)
            
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        
    metadata = {
        "model_id": selected_model_id,
        "feature_version": fe.get_version_hash(),
        "seed": cfg.seed,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "model_type": model_type,
        "model_file": model_path.name
    }
    
    with open(MODELS_DIR / "model_meta.json", "w") as f:
        json.dump(metadata, f, indent=2)
        
    # Write models/selection_report.json
    selection_report = {
        "baseline_metrics": base_metrics,
        "champion_metrics": champ_metrics,
        "selected_model": selected_model_id,
        "reasons": {
            "recall_beats": recall_beats,
            "precision_eq_beat": precision_eq_beat,
            "nasa_no_worse": nasa_no_worse
        }
    }
    
    with open(MODELS_DIR / "selection_report.json", "w") as f:
        json.dump(selection_report, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    train_and_select()
