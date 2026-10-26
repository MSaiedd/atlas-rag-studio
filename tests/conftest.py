"""Deterministic neural substitutes; persistence and Qdrant filtering remain real."""

import hashlib
import os
import re
import uuid

import numpy as np
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import delete

from atlas_rag.api import create_app
from atlas_rag.auth import Identity
from atlas_rag.config import Settings
from atlas_rag.database import Base
from atlas_rag.generation import Prepared
from atlas_rag.retrieval import VectorIndex
from atlas_rag.runtime import Runtime


class TestEncoder:
    __test__ = False
    dimension = 32
    fingerprint = "test_only_32"
    revision = "test-only"
    reranker_revision = "test-only"

    def encode_query(self, value):
        vector = np.zeros(self.dimension)
        for word in re.findall(r"\w+", value.lower()):
            index = (
                int.from_bytes(hashlib.sha256(word.encode()).digest()[:2], "big") % self.dimension
            )
            vector[index] += 1
        return (vector / max(np.linalg.norm(vector), 1)).tolist()

    def encode_documents(self, values):
        return [self.encode_query(value) for value in values]

    def rerank(self, question, passages):
        words = set(re.findall(r"\w+", question.lower()))
        return [
            5.0 if words & set(re.findall(r"\w+", passage.lower())) else -12.0
            for passage in passages
        ]


class TestGenerator:
    __test__ = False
    has_adapter = True
    revision = "test-only"
    answer = "The refund window is fourteen days, subject to review. [1]"

    def prepare(self, question, passages, history=None):
        return Prepared([], list(passages), 20)

    def stream(self, prepared, mode, cancel):
        yield self.answer[:25]
        yield self.answer[25:]


def identity(request: Request):
    return Identity(
        request.headers.get("x-test-tenant", "alpha"),
        request.headers.get("x-test-user", "alice"),
        request.headers.get("x-test-role", "admin"),
    )


@pytest.fixture
def harness(tmp_path):
    url = os.environ.get("ATLAS_TEST_DATABASE_URL", "sqlite:///" + str(tmp_path / "atlas.db"))
    if not url.startswith("sqlite") and url.rsplit("/", 1)[-1] != "atlas_test":
        pytest.fail("PostgreSQL integration tests require a dedicated database named atlas_test")
    settings = Settings(
        database_url=url,
        data_dir=tmp_path,
        qdrant_url=os.environ.get("ATLAS_TEST_QDRANT_URL"),
        qdrant_api_key=os.environ.get("ATLAS_TEST_QDRANT_API_KEY"),
        model_loading=False,
        worker_enabled=False,
    )

    def factory(config, db):
        if not db.sqlite:
            with db.session() as session:
                for table in reversed(Base.metadata.sorted_tables):
                    session.execute(delete(table))
        encoder = TestEncoder()
        encoder.fingerprint = "test_" + uuid.uuid4().hex[:12]
        vectors = VectorIndex(config, encoder.dimension, encoder.fingerprint)
        return Runtime(config, db, encoder, vectors, TestGenerator())

    app = create_app(settings, factory, identity)
    with TestClient(app) as client:
        try:
            yield client, app.state.db, app.state.runtime, settings
        finally:
            if settings.qdrant_url:
                app.state.runtime.vectors.client.delete_collection(app.state.runtime.vectors.name)


def collection(client, headers=None, name="Policies"):
    result = client.post("/api/collections", headers=headers or {}, json={"name": name})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def upload(
    client,
    collection_id,
    content="Refund requests are reviewed within fourteen days.",
    headers=None,
    filename="policy.md",
):
    response = client.post(
        "/api/documents",
        headers=headers or {},
        data={"collection_id": collection_id},
        files={"file": (filename, content.encode(), "text/plain")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def conversation(client, headers=None):
    response = client.post("/api/conversations", headers=headers or {}, json={})
    assert response.status_code == 201
    return response.json()["id"]
