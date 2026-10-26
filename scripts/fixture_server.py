"""CI/browser-only server. Neural components are substitutes; storage and routes are real.

Never use this entry point to serve the product. Real serving uses atlas_rag.api:create_app.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from conftest import TestEncoder, TestGenerator  # noqa: E402

from atlas_rag.api import create_app  # noqa: E402
from atlas_rag.config import Settings  # noqa: E402
from atlas_rag.retrieval import VectorIndex  # noqa: E402
from atlas_rag.runtime import Runtime  # noqa: E402


def factory(settings, db):
    encoder = TestEncoder()
    return Runtime(
        settings,
        db,
        encoder,
        VectorIndex(settings, encoder.dimension, encoder.fingerprint),
        TestGenerator(),
    )


app = create_app(Settings(model_loading=False), factory)
