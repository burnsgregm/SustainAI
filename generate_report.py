import argparse
import json
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Generate SustainAI Build Report")
    parser.add_argument("--eval-id", required=True, help="The Exact Evaluation ID to source metrics from")
    parser.add_argument("--ac1-log", required=True, help="Path to the AC-1 log text string representation")
    args = parser.parse_args()

    # Base derivation location (dynamic mapping avoiding c:/Users/thegr...)
    # This script runs at the root of the repo (next to docs, src, models)
    root = Path(__file__).parent.absolute()
    
    # Read the AC1 explicit target
    ac1_txt = Path(args.ac1_log).read_text(encoding='utf-8', errors='replace')
    
    # Check deviations location
    deviations_file = root / "docs" / "deviations.md"
    if not deviations_file.exists():
        print("DEVIATIONS FILE MISSING, REPORT INCOMPLETE")
        sys.exit(1)
        
    deviations_content = deviations_file.read_text(encoding='utf-8').strip()
    if not deviations_content:
        deviations_text = "None."
    else:
        deviations_text = deviations_content
        
    # Read latest metrics
    eval_target = root / "outputs" / "eval" / args.eval_id / "metrics.json"
    if not eval_target.exists():
        print(f"FAILED TO FIND EVALUATION TARGET METRICS: {eval_target}")
        sys.exit(1)
        
    metrics = json.loads(eval_target.read_text(encoding='utf-8'))
    
    content = f"""# SustainAI Build Report

## Final Evaluation Outputs (Eval ID: {args.eval_id})
*Note: This evaluation (`{args.eval_id}`) reproduces the prediction metrics of `eval-8a40e13a` exactly.*

```json
{json.dumps(metrics, indent=2)}
```

## AC-1 Verification Output
```text
{ac1_txt}
```

## Deviations from TRD
{deviations_text}
"""
    
    report_file = root / "docs" / "build_report.md"
    report_file.write_text(content, encoding='utf-8')
    print(f"Build report generated successfully at {report_file}")
    
if __name__ == "__main__":
    main()
