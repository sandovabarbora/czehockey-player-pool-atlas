.PHONY: help install install-browsers fetch features reduce render all clean test lint check

PYTHON ?= python
VENV   ?= .venv
ACT    := source $(VENV)/bin/activate &&

help:
	@echo "Targets:"
	@echo "  install          Create .venv, install deps with uv (or pip fallback)"
	@echo "  install-browsers Install Playwright browsers (Chromium only)"
	@echo "  fetch            Run all fetchers (NHL, MoneyPuck, Liiga, SHL, NL, Extraliga, IIHF)"
	@echo "  features         Build position-specific feature vectors"
	@echo "  reduce           Run PCA + UMAP + KMeans"
	@echo "  render           Render HTML + PDF report"
	@echo "  all              fetch -> features -> reduce -> render"
	@echo "  test             Run pytest"
	@echo "  lint             Run ruff check"
	@echo "  check            lint + test"
	@echo "  clean            Remove processed data and outputs (keeps raw)"

install:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv $(VENV) && uv pip install -e ".[dev]"; \
	else \
		$(PYTHON) -m venv $(VENV) && $(ACT) pip install -e ".[dev]"; \
	fi

install-browsers:
	$(ACT) playwright install chromium

fetch:
	$(ACT) python -m src.fetch_nhl
	$(ACT) python -m src.fetch_moneypuck
	$(ACT) python -m src.fetch_liiga
	$(ACT) python -m src.fetch_shl
	$(ACT) python -m src.fetch_nl
	$(ACT) python -m src.fetch_extraliga
	$(ACT) python -m src.fetch_iihf
	$(ACT) python -m src.crosswalk

features:
	$(ACT) python -m src.features_forwards
	$(ACT) python -m src.features_defense
	$(ACT) python -m src.features_goalies
	$(ACT) python -m src.trajectory

reduce:
	$(ACT) python -m src.reduce
	$(ACT) python -m src.cluster

render:
	$(ACT) python -m src.render

all: fetch features reduce render

test:
	$(ACT) pytest

lint:
	$(ACT) ruff check src tests

check: lint test

clean:
	rm -rf data/processed/* outputs/*.html outputs/*.pdf outputs/*.svg outputs/*.png
	@echo "Cleaned processed/ and outputs/ (raw/ preserved)"

pages:
	cp outputs/index.html outputs/style.css outputs/atlas_forwards.svg \
	   outputs/atlas_defense.svg outputs/report.pdf docs/
	@echo "Copied current outputs/ to docs/ for GitHub Pages"
