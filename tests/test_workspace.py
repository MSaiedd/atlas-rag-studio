import json
from types import SimpleNamespace

import pytest
from conftest import collection, conversation, upload
from fastapi import HTTPException
from sqlalchemy import func, select

from atlas_rag.api import ChatBody
from atlas_rag.auth import Identity
from atlas_rag.chat import begin_chat
from atlas_rag.database import Document, Job, Message
from atlas_rag.documents import extract_pages, split_pages
from atlas_rag.generation import ABSTENTION, validate_answer
from atlas_rag.retrieval import lexical_search, retrieve


def parse_events(response):
    values = []
    for frame in response.text.split("\n\n"):
        lines = frame.splitlines()
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if data:
            name = next(line[7:] for line in lines if line.startswith("event: "))
            values.append((name, json.loads(data)))
    return values


def test_upload_index_retrieve_and_deduplication(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    doc = upload(client, group)
    assert doc["status"] == "queued"
    assert upload(client, group)["duplicate"]
    with db.session() as session:
        assert session.scalar(select(func.count(Job.id))) == 1
    assert runtime.process_one()
    stored = client.get("/api/documents/" + doc["id"]).json()
    assert stored["status"] == "ready" and stored["chunk_count"] > 0
    result = retrieve(
        db,
        runtime.settings,
        runtime.vectors,
        runtime.encoder,
        Identity("alpha", "alice"),
        "refund",
        [group],
    )
    assert result.passages[0].document_id == doc["id"]
    assert result.candidates[0]["rerank_score"] == 5


def test_tenant_and_user_isolation(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    doc = upload(client, group, "Secret alpha refund policy.")
    runtime.process_one()
    other = {"x-test-tenant": "beta", "x-test-user": "bob"}
    assert client.get("/api/documents", headers=other).json() == []
    assert client.get("/api/documents/" + doc["id"], headers=other).status_code == 404
    assert client.get("/api/documents/" + doc["id"] + "/download", headers=other).status_code == 404
    assert client.delete("/api/documents/" + doc["id"], headers=other).status_code == 404
    assert (
        client.post(
            "/api/documents",
            headers=other,
            data={"collection_id": group},
            files={"file": ("x.txt", b"x")},
        ).status_code
        == 404
    )
    assert (
        retrieve(
            db,
            runtime.settings,
            runtime.vectors,
            runtime.encoder,
            Identity("beta", "bob"),
            "secret refund",
        ).passages
        == []
    )
    chat = conversation(client)
    assert (
        client.get(
            f"/api/conversations/{chat}/messages", headers={"x-test-user": "bob"}
        ).status_code
        == 404
    )


def test_roles_and_cross_origin_boundaries(harness):
    client, _, _, _ = harness
    viewer = {"x-test-role": "viewer"}
    assert (
        client.post("/api/collections", headers=viewer, json={"name": "Forbidden"}).status_code
        == 403
    )
    assert client.get("/api/training/dataset", headers=viewer).status_code == 403
    assert client.get("/api/audit", headers=viewer).status_code == 403
    assert (
        client.post(
            "/api/collections", headers={"Origin": "https://evil.example"}, json={"name": "Forged"}
        ).status_code
        == 403
    )
    assert client.get("/api/workspace", headers={"Host": "evil.example"}).status_code == 400


def test_streaming_persistence_idempotency_and_feedback(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    upload(client, group)
    runtime.process_one()
    chat = conversation(client)
    body = {"question": "refund", "request_id": "request-00000000000001", "mode": "adapted"}
    response = client.post(f"/api/conversations/{chat}/messages", json=body)
    assert response.status_code == 200
    events = parse_events(response)
    assert [kind for kind, _ in events].count("delta") == 2
    answer = next(value for kind, value in events if kind == "complete")
    assert answer["citations"][0]["text"] and answer["trace"]["mode"] == "adapted"
    assert (
        client.post(f"/api/conversations/{chat}/messages", json=body).text.count("event: complete")
        == 1
    )
    with db.session() as session:
        assert session.scalar(select(func.count(Message.id))) == 2
    assert (
        client.patch(f"/api/messages/{answer['id']}/feedback", json={"value": "helpful"}).json()[
            "feedback"
        ]
        == "helpful"
    )
    assert (
        client.patch(
            f"/api/messages/{answer['id']}/feedback",
            headers={"x-test-user": "bob"},
            json={"value": "helpful"},
        ).status_code
        == 404
    )


def test_invalid_citations_are_rejected_without_saving_the_draft(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    upload(client, group)
    runtime.process_one()
    runtime.generator.answer = "Invented secret with a fabricated source. [999]"
    chat = conversation(client)
    events = parse_events(
        client.post(
            f"/api/conversations/{chat}/messages",
            json={"question": "refund", "request_id": "invalid-00000000000001"},
        )
    )
    assert any(kind == "error" and data["clear_draft"] for kind, data in events)
    rows = client.get(f"/api/conversations/{chat}/messages").json()
    assert rows[-1]["state"] == "failed"
    assert "Invented secret" not in rows[-1]["content"]
    assert runtime.generation_slots.acquire(blocking=False)
    runtime.generation_slots.release()


def test_absent_evidence_never_calls_the_generator(harness):
    client, _, runtime, _ = harness

    def forbidden(*args, **kwargs):
        raise AssertionError("Should not generate without evidence")

    runtime.generator.stream = forbidden
    chat = conversation(client)
    response = client.post(
        f"/api/conversations/{chat}/messages",
        json={"question": "unknown question", "request_id": "missing-00000000000001"},
    )
    answer = next(value for kind, value in parse_events(response) if kind == "complete")
    assert answer["content"] == ABSTENTION and not answer["trace"]["model_used"]


def test_deletion_revokes_retrieval_before_vector_cleanup(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    doc = upload(client, group)
    runtime.process_one()
    client.delete("/api/documents/" + doc["id"])
    assert (
        retrieve(
            db,
            runtime.settings,
            runtime.vectors,
            runtime.encoder,
            Identity("alpha", "alice"),
            "refund",
        ).passages
        == []
    )
    assert client.get("/api/documents").json() == []
    assert runtime.process_one()
    with db.session() as session:
        assert (
            not session.get(Document, doc["id"]).file_path
            or session.get(Document, doc["id"]).status == "deleted"
        )


def test_cancellation_and_concurrent_conversation_guard(harness):
    client, db, runtime, _ = harness
    chat = conversation(client)
    identity = Identity("alpha", "alice", "admin")
    body = ChatBody(question="refund policy", request_id="cancel-00000000000001")
    stream = begin_chat(db, runtime, identity, chat, body)
    with pytest.raises(HTTPException) as error:
        begin_chat(
            db,
            runtime,
            identity,
            chat,
            ChatBody(question="second question", request_id="cancel-00000000000002"),
        )
    assert error.value.status_code == 409
    stream.close()  # Also closes a stream that never yielded its first event.
    rows = client.get(f"/api/conversations/{chat}/messages").json()
    assert rows[-1]["state"] == "cancelled"
    second = begin_chat(
        db,
        runtime,
        identity,
        chat,
        ChatBody(question="third question", request_id="cancel-00000000000003"),
    )
    next(second)
    second.close()
    assert client.get(f"/api/conversations/{chat}/messages").json()[-1]["state"] == "cancelled"


def test_upload_failures_retry_and_chunk_boundaries(harness):
    client, _, runtime, _ = harness
    group = collection(client)
    assert (
        client.post(
            "/api/documents",
            data={"collection_id": group},
            files={"file": ("bad.exe", b"anything")},
        ).status_code
        == 415
    )
    bad = upload(client, group, "not a PDF", filename="broken.pdf")
    runtime.process_one()
    assert client.get("/api/documents/" + bad["id"]).json()["status"] == "failed"
    assert client.post("/api/documents/" + bad["id"] + "/retry").status_code == 200
    runtime.process_one()
    assert client.get("/api/documents/" + bad["id"]).json()["error"]
    assert len(split_pages([(1, "# Heading\n\n" + "A long paragraph. " * 200)])) > 1
    with pytest.raises(ValueError):
        extract_pages(b"\x00", "binary.txt", 100)


def test_arabic_lexical_search_and_query_syntax(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    upload(client, group, "سياسة الاسترداد: تقديم الطلب خلال أربعة عشر يوماً.", filename="arabic.md")
    runtime.process_one()
    assert lexical_search(db, "alpha", 'الاسترداد " OR ()', [group], 5)
    assert lexical_search(db, "beta", "الاسترداد", None, 5) == []


def test_citation_validation_contract():
    passages = [SimpleNamespace(text="real evidence")]
    assert validate_answer("A supported answer. [1]", passages) == ([1], False)
    assert validate_answer(ABSTENTION, []) == ([], True)
    with pytest.raises(ValueError):
        validate_answer(
            "This paragraph has no evidence and contains a long unsupported claim.", passages
        )
    with pytest.raises(ValueError):
        validate_answer(
            "A first supported paragraph. [1]\n\nA second paragraph contains a long unsupported claim with no citation.",
            passages,
        )


def test_reindex_does_not_duplicate_passages(harness):
    client, db, runtime, _ = harness
    group = collection(client)
    doc = upload(client, group)
    runtime.process_one()
    before = client.get("/api/documents/" + doc["id"]).json()
    assert client.post("/api/documents/" + doc["id"] + "/reindex").status_code == 200
    assert client.post("/api/documents/" + doc["id"] + "/reindex").status_code == 409
    runtime.process_one()
    after = client.get("/api/documents/" + doc["id"]).json()
    assert after["status"] == "ready"
    assert after["chunk_count"] == before["chunk_count"]
    assert [p["id"] for p in after["passages"]] == [p["id"] for p in before["passages"]]
