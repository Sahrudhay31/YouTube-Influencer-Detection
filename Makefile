# Makefile — YouTube Influencer Detection Pipeline
.PHONY: setup test check dev-sample metrics-readme clean

PYTHON = .venv/Scripts/python.exe
PYTEST = .venv/Scripts/pytest.exe

setup:
	uv venv --python 3.11 .venv
	uv pip install --python $(PYTHON) -r requirements.txt

test:
	$(PYTEST) tests/unit tests/spark -v

check:
	$(PYTHON) scripts/check_all.py

dev-sample:
	$(PYTHON) -m src.ingestion.load_youniverse --dev --raw-dir data/raw/youniverse

metrics-readme:
	$(PYTHON) scripts/update_readme_metrics.py

clean:
	rm -rf .pytest_cache htmlcov .coverage
