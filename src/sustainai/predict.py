"""SustainAI prediction service.

Boundary: loads the serialized model and makes predictions on data.
Outputs prediction records.
Implements TRD Section 7.2 (FR-PRD-1, FR-PRD-2).
"""

from __future__ import annotations

import json
import logging
import pickle
import joblib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from sustainai.config import DATA_DIR, MODELS_DIR, get_config
from sustainai.features import FeatureEngineer
from sustainai.schemas import PredictionRecord, Split

logger = logging.getLogger(__name__)

FEATURES_DIR = DATA_DIR / "features"


class Predictor:
    """Wrapper that loads the model and prepares it for prediction."""
    
    def __init__(self):
        meta_path = MODELS_DIR / "model_meta.json"
        with open(meta_path, "r") as f:
            self.metadata = json.load(f)
            
        self.model_id = self.metadata["model_id"]
        self.model_type = self.metadata["model_type"]
        self.feature_version = self.metadata["feature_version"]
        
        model_file = MODELS_DIR / self.metadata["model_file"]
        if self.model_type == "keras":
            import tensorflow as tf
            self.model = tf.keras.models.load_model(model_file)
        else:
            self.model = joblib.load(model_file)
                
        with open(MODELS_DIR / "feature_scaler.pkl", "rb") as f:
            self.feature_engineer: FeatureEngineer = pickle.load(f)
            
        self.rul_cap = get_config().data.rul_cap
            
    def predict(self, features_df: pd.DataFrame, run_id: str) -> list[PredictionRecord]:
        """Predict RUL on the given feature data.
        
        Note: The caller must provide the features_df containing the feature matrix,
        including 'unit_id' and 'cycle'. For FR-PRD-1, we predict at the latest observed cycle.
        """
        # Ensure we only predict at the latest cycle for each unit
        # Sorting by unit_id and cycle to be safe
        features_df = features_df.sort_values(["unit_id", "cycle"])
        latest = features_df.groupby("unit_id").tail(1).copy()
        
        # Get purely the feature columns needed by model
        feature_cols = self.feature_engineer.feature_columns
        X = latest[feature_cols].values
        
        if self.model_type == "keras":
            preds = self.model.predict(X, verbose=0).flatten()
        else:
            preds = self.model.predict(X)
            
        # FR-PRD-2: Clip predictions
        preds = np.clip(preds, 0, self.rul_cap)
        
        records = []
        now = datetime.now(timezone.utc)
        
        for i, row in enumerate(latest.itertuples()):
            record = PredictionRecord(
                unit_id=row.unit_id,
                cycle=row.cycle,
                predicted_rul=float(preds[i]),
                model_id=self.model_id,
                feature_version=self.feature_version,
                run_id=run_id,
                created_at=now
            )
            records.append(record)
            
        return records


def run_predictions(split: Split, run_id: str | None = None) -> list[PredictionRecord]:
    """Run predictions on the specified dataset split."""
    if run_id is None:
        run_id = str(uuid.uuid4())
        
    predictor = Predictor()
    split_filename = f"{split.value}.parquet"
    feat_df = pd.read_parquet(FEATURES_DIR / split_filename)
    
    records = predictor.predict(feat_df, run_id=run_id)
    return records


def main() -> None:
    """Entry point for `python -m sustainai.predict`."""
    # When run as a pipeline step (e.g. `make run`), predict on test split
    cfg = get_config()
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    
    logger.info("Starting prediction pass on TEST split...")
    records = run_predictions(Split.TEST, run_id)
    
    logger.info("Generated %d predictions for run %s", len(records), run_id)
    
    # Save predictions as an artifact for the next stage (exception generator)
    out_dir = DATA_DIR / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # We serialize as JSON to easily pass boundaries
    out_file = out_dir / "predictions.json"
    with open(out_file, "w") as f:
        # Pydantic 2.x dump
        json.dump([r.model_dump(mode='json') for r in records], f, indent=2)
        
    logger.info("Predictions saved to %s", out_file)
    print(run_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
