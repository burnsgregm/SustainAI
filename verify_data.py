"""Verify C-MAPSS FD001 data files."""
import pandas as pd
import os

data_dir = "data/raw"
files = {
    "train_FD001.txt": {"expect_units": 100, "expect_cols": 26},
    "test_FD001.txt": {"expect_units": 100, "expect_cols": 26},
    "RUL_FD001.txt": {"expect_lines": 100},
}

all_ok = True
for fname, checks in files.items():
    fpath = os.path.join(data_dir, fname)
    if not os.path.exists(fpath):
        print(f"MISSING: {fname}")
        all_ok = False
        continue

    df = pd.read_csv(fpath, header=None, sep=r"\s+")

    if "expect_lines" in checks:
        ok = len(df) == checks["expect_lines"]
        print(f"{fname}: {len(df)} lines (expect {checks['expect_lines']}) {'PASS' if ok else 'FAIL'}")
        if not ok:
            all_ok = False
    else:
        units = df[0].nunique()
        cols = df.shape[1]
        ok_u = units == checks["expect_units"]
        ok_c = cols == checks["expect_cols"]
        print(f"{fname}: {units} units (expect {checks['expect_units']}) {'PASS' if ok_u else 'FAIL'}, "
              f"{cols} cols (expect {checks['expect_cols']}) {'PASS' if ok_c else 'FAIL'}")
        if not (ok_u and ok_c):
            all_ok = False

if all_ok:
    print("\nALL VERIFICATION CHECKS PASSED")
else:
    print("\nSOME CHECKS FAILED")
    exit(1)
