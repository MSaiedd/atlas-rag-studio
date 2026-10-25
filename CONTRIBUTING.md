# Contributing

Use Python 3.11 or 3.12 and a virtual environment. Install `pip install -e '.[dev]'`.
Run `ruff check .`, `ruff format --check .`, and `pytest` before opening a pull request.
Include a reproducible example for bugs. Keep synthetic fixtures free of personal data.
Never add credentials, model caches, or real customer records to commits.
Comments should explain design decisions or invariants; docstrings describe public interfaces.
