# Validation status

Validated locally on 2026-10-25 with Python 3.12.3. Exact commands and results are recorded
below. Portfolio fixtures are synthetic; passing checks do not establish production readiness.

## Automated checks

- `ruff check .` — passed.
- `ruff format --check .` — passed.
- `pytest --cov=src --cov-report=term-missing` — see the recorded test log in `reports/tests.txt`.
- `python scripts/browser_smoke.py` — passed: real Chromium desktop flow, 390 px mobile layout,
  no uncaught browser errors. Screenshots are in `docs/screenshots/`.

GitHub Actions repeats lint, tests on Python 3.11/3.12, and browser validation after publishing.
Local evidence is separate from hosted CI status.

## Boundaries

Static bearer tokens are development identities. No public hosting or production rollout was performed.
Optional external providers and CUDA-dependent paths require their own runtime validation.

## Packaging

`python -m build --wheel --outdir dist` — passed. The wheel includes HTML/CSS/JavaScript assets.

## Agent boundary

The real browser run exercised the offline deterministic workflow, pending refund approval,
and audit events. Unit tests exercised concurrent decisions and forbidden-tool handling
with a simulated model reply. A live Ollama model and any real payment provider were not used.
