"""SustainAI data ingestion.

Boundary: reads raw C-MAPSS FD001 text files, validates them, computes
RUL labels, and writes canonical Parquet. Knows nothing about models or
features. Implements TRD Section 4 (FR-ING-1 through FR-ING-5).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from sustainai.config import DATA_DIR, get_config
from sustainai.schemas import RAW_COLUMNS, Split

logger = logging.getLogger(__name__)

RAW_DIR = DATA_DIR / "raw"
CANONICAL_DIR = DATA_DIR / "canonical"

TRAIN_FILE = "train_FD001.txt"
TEST_FILE = "test_FD001.txt"
RUL_FILE = "RUL_FD001.txt"


class IngestionError(Exception):
    """Raised when ingestion validation fails."""
    pass


def _parse_raw_file(filepath: Path) -> pd.DataFrame:
    """Parse a raw C-MAPSS space-delimited text file.

    FR-ING-1: Reject on wrong column count, non-numeric values, or
    non-monotonic cycles per unit.
    """
    if not filepath.exists():
        raise IngestionError(f"File not found: {filepath}")

    df = pd.read_csv(filepath, header=None, sep=r"\s+")

    # FR-ING-1: Check column count
    if df.shape[1] != 26:
        raise IngestionError(
            f"{filepath.name}: expected 26 columns, got {df.shape[1]}"
        )

    df.columns = RAW_COLUMNS

    # FR-ING-1: Check types (all should be numeric)
    for col in df.columns:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise IngestionError(
                f"{filepath.name}: column '{col}' contains non-numeric values"
            )

    # FR-ING-1: Check monotonic cycles per unit
    for unit_id, group in df.groupby("unit_id"):
        cycles = group["cycle"].values
        if not np.all(np.diff(cycles) == 1):
            bad_idx = np.where(np.diff(cycles) != 1)[0]
            raise IngestionError(
                f"{filepath.name}: unit {unit_id} has non-monotonic cycles "
                f"at positions {bad_idx.tolist()}"
            )

    return df


def _compute_train_rul(df: pd.DataFrame, rul_cap: int) -> pd.DataFrame:
    """Compute RUL labels for training data.

    FR-ING-2: rul = min(max_cycle(unit) - cycle, rul_cap)
    """
    max_cycles = df.groupby("unit_id")["cycle"].transform("max")
    df["rul"] = (max_cycles - df["cycle"]).clip(upper=rul_cap).astype(int)
    return df


def _attach_test_rul(
    test_df: pd.DataFrame, rul_path: Path
) -> pd.DataFrame:
    """Attach true RUL to each test unit's final cycle.

    FR-ING-3: true RUL from RUL_FD001.txt, by unit order.
    """
    rul_values = pd.read_csv(rul_path, header=None, sep=r"\s+")

    if len(rul_values) != test_df["unit_id"].nunique():
        raise IngestionError(
            f"RUL file has {len(rul_values)} entries but test file has "
            f"{test_df['unit_id'].nunique()} units"
        )

    # Map unit IDs (1-indexed, in order) to their true RUL
    unit_ids = sorted(test_df["unit_id"].unique())
    rul_map = dict(zip(unit_ids, rul_values.iloc[:, 0].values))

    # Find the final cycle for each unit
    final_mask = test_df.groupby("unit_id")["cycle"].transform("max") == test_df["cycle"]
    test_df["true_rul_final"] = np.where(
        final_mask,
        test_df["unit_id"].map(rul_map),
        np.nan,
    )
    # Convert to nullable int
    test_df["true_rul_final"] = test_df["true_rul_final"].astype("Int64")

    return test_df


def ingest(raw_dir: Path | None = None, output_dir: Path | None = None) -> Path:
    """Run the full ingestion pipeline.

    FR-ING-4: Write canonical Parquet to data/canonical/.
    Idempotent: re-running on the same inputs overwrites identically.

    Returns the path to the canonical Parquet file.
    """
    cfg = get_config()
    raw_dir = raw_dir or RAW_DIR
    output_dir = output_dir or CANONICAL_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting ingestion from %s", raw_dir)

    # Parse raw files
    train_df = _parse_raw_file(raw_dir / TRAIN_FILE)
    test_df = _parse_raw_file(raw_dir / TEST_FILE)

    # Verify counts
    n_train = train_df["unit_id"].nunique()
    n_test = test_df["unit_id"].nunique()
    logger.info("Train: %d units, %d rows", n_train, len(train_df))
    logger.info("Test: %d units, %d rows", n_test, len(test_df))

    if n_train != 100:
        raise IngestionError(f"Expected 100 train units, got {n_train}")
    if n_test != 100:
        raise IngestionError(f"Expected 100 test units, got {n_test}")

    # Compute training RUL labels (FR-ING-2)
    train_df = _compute_train_rul(train_df, cfg.data.rul_cap)
    train_df["true_rul_final"] = pd.array([pd.NA] * len(train_df), dtype="Int64")
    train_df["split"] = Split.TRAIN.value

    # Attach test RUL (FR-ING-3)
    test_df["rul"] = pd.array([pd.NA] * len(test_df), dtype="Int64")
    test_df = _attach_test_rul(test_df, raw_dir / RUL_FILE)
    test_df["split"] = Split.TEST.value

    # Combine and write Parquet (FR-ING-4)
    canonical = pd.concat([train_df, test_df], ignore_index=True)

    output_path = output_dir / "fd001_canonical.parquet"
    canonical.to_parquet(output_path, index=False, engine="pyarrow")
    logger.info("Canonical Parquet written to %s (%d rows)", output_path, len(canonical))

    return output_path


def main() -> None:
    """Entry point for `python -m sustainai.ingest`."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output_path = ingest()
    print(f"Ingestion complete: {output_path}")


if __name__ == "__main__":
    main()
