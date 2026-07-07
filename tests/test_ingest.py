import pandas as pd
import pytest
from pathlib import Path

from sustainai.ingest import _parse_raw_file, IngestionError, _compute_train_rul

# Create dummy raw data for testing
def create_dummy_raw_file(tmp_path: Path, filename: str, content: str) -> Path:
    file_path = tmp_path / filename
    with open(file_path, "w") as f:
        f.write(content)
    return file_path

# =============================================================================
# T-1: Ingestion rejects malformed input
# =============================================================================

def test_reject_wrong_column_count(tmp_path: Path):
    """T-1: Should reject input with incorrect number of columns."""
    content = "1 1 " + " ".join(["10.0"] * 23) + "\n"  # 1+1+23 = 25 columns
    fpath = create_dummy_raw_file(tmp_path, "wrong_cols.txt", content)
    
    with pytest.raises(IngestionError, match="expected 26 columns, got 25"):
        _parse_raw_file(fpath)

def test_reject_non_numeric(tmp_path: Path):
    """T-1: Should reject non-numeric values in the columns."""
    content = "1 1 foo " + " ".join(["10.0"] * 23) + "\n"
    fpath = create_dummy_raw_file(tmp_path, "non_numeric.txt", content)
    
    # pandas actually falls back to reading "foo" as object, we should catch it or it raises error internally.
    # Ingestion error should trigger when checking if numeric.
    with pytest.raises(IngestionError, match="column 'op_setting_1' contains non-numeric values"):
        _parse_raw_file(fpath)

def test_reject_non_monotonic_cycles(tmp_path: Path):
    """T-1: Should reject non-monotonic cycles for a unit."""
    # Unit 1: 1, 2, 4 (missing 3) -> should not matter if step is not just monotonically increasing, but TRD specifically requested monotonic step 1.
    content = (
        "1 1 " + " ".join(["10.0"] * 24) + "\n"
        "1 2 " + " ".join(["10.0"] * 24) + "\n"
        "1 4 " + " ".join(["10.0"] * 24) + "\n" # Non-monotonic step 1
    )
    fpath = create_dummy_raw_file(tmp_path, "non_monotonic.txt", content)
    
    with pytest.raises(IngestionError, match="unit 1 has non-monotonic cycles"):
        _parse_raw_file(fpath)

# =============================================================================
# T-2: RUL labeling correct at boundaries
# =============================================================================

def test_rul_labeling_boundaries():
    """T-2: RUL labeling correct at boundaries (cap applied; final cycle rul = 0 for train units)."""
    # Create simple dataframe simulating parsed training data
    df = pd.DataFrame({
        "unit_id": [1, 1, 1, 1, 2, 2, 2],
        "cycle": [1, 2, 3, 200, 1, 2, 3] # Simulating long and short run
    })
    
    test_cap = 10
    
    processed = _compute_train_rul(df, rul_cap=test_cap)
    
    rul_unit1 = processed[processed["unit_id"] == 1]["rul"].tolist()
    rul_unit2 = processed[processed["unit_id"] == 2]["rul"].tolist()
    
    # Unit 1's final cycle is 200.
    assert rul_unit1[-1] == 0, "T-2: final cycle rul = 0 for train units"
    assert rul_unit1[0] == 10, "T-2: early cycles capped at rul_cap"
    assert rul_unit1[-2] == 10, "Cycle 3 has RUL 197, capped to 10"

    # Unit 2's final cycle is 3.
    assert rul_unit2[-1] == 0
    assert rul_unit2[-2] == 1 # 3 - 2 = 1, not capped
    assert rul_unit2[0] == 2 # 3 - 1 = 2, not capped


def test_t1_rul_file_mismatch(tmp_path: Path):
    """T-1: Verify IngestionError raised on test dataset vs RUL file count mismatch."""
    from sustainai.ingest import _attach_test_rul
    
    # Create a 2-line RUL file
    rul_path = create_dummy_raw_file(tmp_path, "RUL_FD001.txt", "112\n130\n")
    
    # Create test_df with 3 unique units
    test_df = pd.DataFrame({
        "unit_id": [1, 2, 3],
        "cycle": [1, 1, 1]
    })
    
    with pytest.raises(IngestionError, match="has 2 entries but test file has 3 units"):
        _attach_test_rul(test_df, str(rul_path))
