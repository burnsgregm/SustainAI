.PHONY: setup ingest features train run triage evaluate test serve docker-build clean

PYTHON ?= python

setup:
	$(PYTHON) -m pip install -e ".[dev]"

ingest:
	$(PYTHON) -m sustainai.ingest

features:
	$(PYTHON) -m sustainai.features

train:
	$(PYTHON) -m sustainai.train

run:
	$(PYTHON) -m sustainai.predict

triage:
	$(PYTHON) -m sustainai.agent.triage_agent

evaluate:
	$(PYTHON) -m sustainai.harness.evaluate

test:
	$(PYTHON) -m pytest tests/ -v

serve:
	$(PYTHON) -m uvicorn sustainai.api:app --host 0.0.0.0 --port 8000

docker-build:
	docker build -f docker/Dockerfile -t sustainai:latest .

clean:
	rm -rf data/canonical/ data/features/ outputs/ models/*.joblib models/*.keras
