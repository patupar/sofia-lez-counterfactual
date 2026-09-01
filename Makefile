.PHONY: install test lint sample

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	python -m ruff check .

sample:
	python -m sofia_lez --config configs/sample.yaml run --skip-download
