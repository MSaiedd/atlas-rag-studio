# Contributing

Use Python 3.11/3.12 and Node.js 22.12+. Install `pip install -e '.[dev,browser]'` and
`npm ci --prefix frontend`. Model dependencies are optional for most regression checks.

Before a pull request:

```bash
ruff check .
ruff format --check .
pytest
npm run check --prefix frontend
npm test --prefix frontend
npm audit --prefix frontend --audit-level=moderate
npm run build --prefix frontend
python scripts/browser_smoke.py
```

Browser CI uses neural substitutes. Keep that distinction explicit. Record actual model runs
separately, including revisions, dataset hashes, seeds, hardware and limitations. Never fabricate
benchmark results or describe lexical fact coverage as semantic faithfulness.

Keep workspace isolation, deletion visibility, request idempotency, cancellation cleanup and
reference validation covered by meaningful tests. Use a dedicated `atlas_test` database for
PostgreSQL integration tests; the harness clears its fixture records.

Update the README, architecture/deployment notes and validation evidence when behavior changes.
Do not commit real credentials, customer documents, model caches, or private runtime databases.
