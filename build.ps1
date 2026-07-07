Write-Host "Running AC-1 Validation Flow"

# Ensure we run in a dedicated venv correctly isolated
if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..."
    & "C:\Users\thegr\AppData\Local\Programs\Python\Python310\python.exe" -m venv .venv
}

# Prepend .venv to path to simulate activation
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"

Write-Host "setup"
python -m pip install -e .[dev]

Write-Host "ingest"
python -m sustainai.ingest

Write-Host "features"
python -m sustainai.features

Write-Host "train"
python -m sustainai.train

Write-Host "tune"
python -m sustainai.exceptions

Write-Host "predict"
python -m sustainai.predict

Write-Host "evaluate"
$evalOutput = python -m sustainai.harness.evaluate
$evalId = ""
foreach ($line in $evalOutput) {
    if ($line -match "Eval ID:\s*([a-zA-Z0-9-]+)") {
        $evalId = $matches[1]
    }
}
Write-Host $evalOutput

if ($evalId -eq "") {
    Write-Error "Failed to extract eval ID!"
}

Write-Host "test"
pytest tests/

Write-Host "AC-1 RUN COMPLETE"
