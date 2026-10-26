"""Stream real model drafts, validate references, then persist a final answer."""

import json
import threading
import time

from fastapi import HTTPException
from sqlalchemy import select

from .database import Chunk, Conversation, Document, Message, new_id
from .generation import abstention_for, validate_answer
from .retrieval import retrieve


def conversation_for(session, identity, conversation_id):
    row = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant == identity.tenant,
            Conversation.user == identity.user,
        )
    )
    if row is None:
        raise HTTPException(404, "Conversation not found")
    return row


def hydrate_citations(session, tenant, citations):
    ids = [c["chunk_id"] for c in citations]
    rows = (
        {
            chunk.id: chunk
            for chunk in session.scalars(
                select(Chunk)
                .join(Document, Chunk.document_id == Document.id)
                .where(
                    Chunk.id.in_(ids),
                    Chunk.tenant == tenant,
                    Document.tenant == tenant,
                    Document.status == "ready",
                )
            )
        }
        if ids
        else {}
    )
    return [
        {
            **citation,
            "text": rows[citation["chunk_id"]].text if citation["chunk_id"] in rows else "",
            "available": citation["chunk_id"] in rows,
        }
        for citation in citations
    ]


def message_dict(session, row):
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "state": row.state,
        "citations": hydrate_citations(session, row.tenant, row.citations),
        "trace": row.trace,
        "feedback": row.feedback,
        "created_at": row.created_at,
    }


def event(name, value):
    return f"event: {name}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"


class ManagedStream:
    """Release a reserved slot even if the client disconnects before the first event."""

    def __init__(self, iterator, db, runtime, message_id):
        self.iterator, self.db, self.runtime, self.message_id = iterator, db, runtime, message_id
        self.started, self.closed = False, False

    def __iter__(self):
        return self

    def __next__(self):
        self.started = True
        return next(self.iterator)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.started:
            self.iterator.close()
        else:
            try:
                with self.db.session() as session:
                    row = session.get(Message, self.message_id)
                    if row and row.state == "generating":
                        row.state, row.content = "cancelled", "Answer generation was stopped."
            finally:
                self.runtime.generation_slots.release()


def begin_chat(db, runtime, identity, conversation_id, body):
    from sqlalchemy.exc import IntegrityError

    if not runtime.ready:
        raise HTTPException(503, runtime.error or "Knowledge models are warming up")
    if body.mode == "adapted" and not runtime.generator.has_adapter:
        raise HTTPException(
            409, "No grounding adapter is loaded. Choose the base model or import a training run"
        )
    acquired = False
    try:
        with db.session() as session:
            conversation = conversation_for(session, identity, conversation_id)
            previous = session.scalar(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.request_id == body.request_id,
                )
            )
            if previous:
                if previous.state == "generating":
                    raise HTTPException(409, "This message is already being answered")
                return [event("complete", message_dict(session, previous))]
            if session.scalar(
                select(Message.id).where(
                    Message.conversation_id == conversation_id, Message.state == "generating"
                )
            ):
                raise HTTPException(409, "This conversation already has an active answer")
            if not runtime.generation_slots.acquire(blocking=False):
                raise HTTPException(
                    429,
                    "All answer slots are occupied. Try again shortly",
                    headers={"Retry-After": "5"},
                )
            acquired = True
            history = [
                {"role": row.role, "content": row.content}
                for row in session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id, Message.state == "complete")
                    .order_by(Message.created_at)
                )
            ][-6:]
            row = Message(
                id=new_id(),
                tenant=identity.tenant,
                conversation_id=conversation_id,
                role="assistant",
                state="generating",
                request_id=body.request_id,
            )
            session.add(
                Message(
                    tenant=identity.tenant,
                    conversation_id=conversation_id,
                    role="user",
                    content=body.question,
                    created_at=time.time() - 0.001,
                )
            )
            session.add(row)
            conversation.title = (
                body.question[:90]
                if conversation.title == "New conversation"
                else conversation.title
            )
            conversation.updated_at = time.time()
            message_id = row.id
        return ManagedStream(
            stream_answer(db, runtime, identity, message_id, body, history), db, runtime, message_id
        )
    except IntegrityError as error:
        if acquired:
            runtime.generation_slots.release()
        raise HTTPException(
            409, "Another answer for this conversation was accepted first"
        ) from error
    except Exception:
        if acquired:
            runtime.generation_slots.release()
        raise


def stream_answer(db, runtime, identity, message_id, body, history):
    cancel = threading.Event()
    started = time.perf_counter()
    trace = {
        "mode": body.mode,
        "model": runtime.settings.model_id,
        "model_revision": runtime.generator.revision,
        "request_id": body.request_id,
    }
    completed = False
    try:
        yield event("status", {"stage": "retrieving", "label": "Searching your knowledge"})
        # Expand short follow-ups using the last user question; this is explicit query expansion.
        previous_questions = [m["content"] for m in history if m["role"] == "user"]
        search_query = body.question
        if previous_questions and len(body.question.split()) < 8:
            search_query = previous_questions[-1] + "\nFollow-up: " + body.question
        result = retrieve(
            db,
            runtime.settings,
            runtime.vectors,
            runtime.encoder,
            identity,
            search_query,
            body.collection_ids or None,
        )
        trace.update(result.timings)
        trace.update(
            retrieval_query=search_query,
            candidates=result.candidates,
            candidate_count=len(result.candidates),
        )
        if not result.passages:
            answer, citations, abstained = abstention_for(body.question), [], True
            trace.update(model_used=False, prompt_tokens=0)
        else:
            prepared = runtime.generator.prepare(body.question, result.passages, history)
            sources = [
                {
                    "ref": i,
                    "chunk_id": p.id,
                    "document_id": p.document_id,
                    "title": p.title,
                    "filename": p.filename,
                    "page": p.page,
                    "heading": p.heading,
                    "text": p.text,
                    "rerank_score": round(p.rerank_score, 4),
                    "available": True,
                }
                for i, p in enumerate(prepared.passages, 1)
            ]
            yield event("sources", sources)
            yield event(
                "status", {"stage": "generating", "label": "Writing from retrieved evidence"}
            )
            pieces, first_token = [], None
            generation_started = time.perf_counter()
            for piece in runtime.generator.stream(prepared, body.mode, cancel):
                if first_token is None:
                    first_token = time.perf_counter()
                pieces.append(piece)
                yield event("delta", {"text": piece})
            answer = "".join(pieces).strip()
            refs, abstained = validate_answer(answer, prepared.passages)
            citations = [
                {k: v for k, v in source.items() if k not in {"text", "available"}}
                for source in sources
                if source["ref"] in refs
            ]
            trace.update(
                model_used=True,
                prompt_tokens=prepared.prompt_tokens,
                generation_ms=round((time.perf_counter() - generation_started) * 1000, 2),
                ttft_ms=round((first_token - started) * 1000, 2) if first_token else None,
            )
        trace.update(
            total_ms=round((time.perf_counter() - started) * 1000, 2),
            abstained=abstained,
            citation_count=len(citations),
        )
        with db.session() as session:
            row = session.get(Message, message_id)
            if row is None:
                return
            row.content, row.citations, row.trace, row.state = answer, citations, trace, "complete"
            session.flush()
            payload = message_dict(session, row)
        completed = True
        yield event("complete", payload)
    except GeneratorExit:
        raise
    except Exception as error:
        trace.update(
            error_type=type(error).__name__,
            total_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        with db.session() as session:
            row = session.get(Message, message_id)
            if row:
                row.content = "I couldn't verify an answer against the selected evidence. Try a more specific question or review the sources."
                row.state, row.trace = "failed", trace
        completed = True
        yield event(
            "error",
            {
                "message": "The answer could not pass evidence validation. No unverified draft was saved.",
                "clear_draft": True,
                "message_id": message_id,
            },
        )
    finally:
        cancel.set()
        if not completed:
            with db.session() as session:
                row = session.get(Message, message_id)
                if row and row.state == "generating":
                    row.state, row.content, row.trace = (
                        "cancelled",
                        "Answer generation was stopped.",
                        trace,
                    )
        runtime.generation_slots.release()
