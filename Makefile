.PHONY: help install install-browsers fetch features reduce render all clean test lint check \
	fetch-nhl fetch-eurostat fetch-liiga fetch-shl fetch-extraliga verify-snapshot restore-snapshot \
	analysis analysis-fast pages

PYTHON ?= python
VENV   ?= .venv
ACT    := source $(VENV)/bin/activate &&

help:
	@echo "Targets:"
	@echo "  install          Create .venv from uv.lock with uv sync (or pip fallback)"
	@echo "  install-browsers Install Playwright browsers (Chromium only)"
	@echo "  fetch            Run all fetchers (NHL, MoneyPuck, Liiga, SHL, NL, Extraliga, IIHF)"
	@echo "  fetch-nhl        NHL skaters, goalies and careers 1995/96-2025/26 -> data/snapshot/"
	@echo "  fetch-eurostat   Eurostat 1 January population 1995-2026 -> data/snapshot/"
	@echo "  fetch-liiga      Liiga skaters and goalies 1995/96-2025/26 -> data/snapshot/"
	@echo "  fetch-shl        SHL skaters and goalies 1995/96-2025/26 -> data/snapshot/"
	@echo "  fetch-extraliga  Extraliga skaters, goalies, birth dates 1995/96-2025/26 (hokej.cz, ~1 h cold)"
	@echo "  verify-snapshot  Check data/snapshot/ against its SHA256SUMS"
	@echo "  analysis         Spec questions 1-7, linking and the pool list -> outputs/*.json (~6 min, PyMC)"
	@echo "  analysis-fast    The same without refitting the break model (q2)"
	@echo "  restore-snapshot Copy data/snapshot/ into data/processed/ (never overwrites newer files)"
	@echo "  features         Build position-specific feature vectors"
	@echo "  reduce           Run PCA + UMAP + KMeans"
	@echo "  render           Render the legacy HTML + PDF report (not the site)"
	@echo "  pages            Render the site (summary, q/<slug>/, methodology/, players/ ...) from outputs/"
	@echo "  all              fetch -> features -> reduce -> render"
	@echo "  test             Run pytest"
	@echo "  lint             Run ruff check"
	@echo "  check            lint + test"
	@echo "  clean            Remove processed data and outputs (keeps raw)"

install:
	@if command -v uv >/dev/null 2>&1; then \
		UV_PROJECT_ENVIRONMENT=$(VENV) uv sync --extra dev; \
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

fetch-nhl:
	$(ACT) python -m src.fetch.nhl

fetch-eurostat:
	$(ACT) python -m src.fetch.eurostat

fetch-liiga:
	$(ACT) python -m src.fetch.liiga

fetch-shl:
	$(ACT) python -m src.fetch.shl

fetch-extraliga:
	$(ACT) python -m src.fetch.extraliga

verify-snapshot:
	$(ACT) python -m src.snapshot verify

analysis:
	$(ACT) python -m src.analysis

analysis-fast:
	$(ACT) python -m src.analysis --skip-model

restore-snapshot:
	$(ACT) python -m src.snapshot restore

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
	# The summary, one page per question, this-autumn/, methodology/ and players/ from outputs/*.json:
	# src/web renders templates/site/ and copies its static assets; CNAME and img/ stay.
	./site/build.sh
	@echo "Built docs/ for GitHub Pages (English)"
