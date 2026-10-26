"""Authenticated workspace API and same-origin React application."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import anyio
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .auth import Authentication
from .chat import begin_chat, conversation_for, message_dict
from .config import Settings
from .database import (
    Audit,
    Chunk,
    Collection,
    Conversation,
    Database,
    Document,
    Experiment,
    Job,
    Message,
)
from .documents import collection_for, document_dict, remove_document, upload_document
from .runtime import Runtime


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollectionBody(Payload):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    color: Literal["indigo", "teal", "amber", "rose"] = "indigo"


class ConversationBody(Payload):
    title: str = Field(default="New conversation", min_length=1, max_length=160)


class ChatBody(Payload):
    question: str = Field(min_length=2, max_length=2000)
    request_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    mode: Literal["base", "adapted"] = "base"
    collection_ids: list[str] = Field(default_factory=list, max_length=20)


class FeedbackBody(Payload):
    value: Literal["helpful", "unhelpful"] | None


def create_app(settings=None, runtime_factory=Runtime, identity_override=None):
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.database_url)
    runtime = runtime_factory(settings, db)
    auth = identity_override or Authentication(settings)

    @asynccontextmanager
    async def lifespan(app):
        runtime.start()
        yield
        runtime.close()
        db.engine.dispose()

    app = FastAPI(title="Atlas RAG Studio", version=__version__, lifespan=lifespan)
    app.state.db, app.state.runtime = db, runtime
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=[h.strip() for h in settings.allowed_hosts.split(",")]
    )

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            parsed = urlsplit(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme not in {
                "http",
                "https",
            }:
                return JSONResponse(
                    {"detail": "Cross-origin writes are not allowed"}, status_code=403
                )
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "same-origin",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            }
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return {
            "status": "ready" if runtime.ready else "loading" if not runtime.error else "degraded",
            "models_ready": runtime.ready,
            "error": runtime.error,
            "version": __version__,
        }

    @app.get("/ready", include_in_schema=False)
    def ready():
        if not runtime.ready:
            raise HTTPException(503, "Models are not ready")
        return {"ready": True}

    @app.get("/api/workspace")
    def workspace(identity=Depends(auth)):
        with db.session() as session:
            documents = list(
                session.scalars(
                    select(Document).where(
                        Document.tenant == identity.tenant, Document.status != "deleted"
                    )
                )
            )
            collections = list(
                session.scalars(
                    select(Collection)
                    .where(Collection.tenant == identity.tenant)
                    .order_by(Collection.created_at)
                )
            )
            counts = {c.id: sum(d.collection_id == c.id for d in documents) for c in collections}
            answer_count = session.scalar(
                select(func.count(Message.id))
                .join(Conversation)
                .where(
                    Conversation.tenant == identity.tenant,
                    Conversation.user == identity.user,
                    Message.role == "assistant",
                    Message.state == "complete",
                )
            )
            return {
                "name": "Northstar workspace" if settings.auth_mode == "local" else identity.tenant,
                "identity": {
                    "user": identity.user,
                    "role": identity.role,
                    "auth_mode": settings.auth_mode,
                },
                "collections": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "description": c.description,
                        "color": c.color,
                        "document_count": counts[c.id],
                    }
                    for c in collections
                ],
                "stats": {
                    "documents": len(documents),
                    "ready_documents": sum(d.status == "ready" for d in documents),
                    "chunks": sum(d.chunk_count for d in documents if d.status == "ready"),
                    "answers": answer_count,
                },
                "models": {
                    "ready": runtime.ready,
                    "error": runtime.error,
                    "base": settings.model_id,
                    "base_revision": settings.model_revision,
                    "embedding": settings.embedding_model,
                    "reranker": settings.reranker_model,
                    "adapted_available": runtime.ready and runtime.generator.has_adapter,
                    "backend": settings.llm_backend,
                },
            }

    @app.post("/api/collections", status_code=201)
    def new_collection(body: CollectionBody, identity=Depends(auth)):
        identity.require_editor()
        if not body.name.strip():
            raise HTTPException(422, "Collection name cannot be blank")
        with db.session() as session:
            row = Collection(
                tenant=identity.tenant,
                name=body.name.strip(),
                description=body.description,
                color=body.color,
            )
            session.add(row)
            session.flush()
            return {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "color": row.color,
                "document_count": 0,
            }

    @app.get("/api/documents")
    def documents(collection_id: str | None = None, identity=Depends(auth)):
        with db.session() as session:
            query = select(Document).where(
                Document.tenant == identity.tenant, Document.status != "deleted"
            )
            if collection_id:
                collection_for(session, identity, collection_id)
                query = query.where(Document.collection_id == collection_id)
            return [
                document_dict(row)
                for row in session.scalars(query.order_by(Document.created_at.desc()))
            ]

    @app.post("/api/documents", status_code=202)
    async def upload(
        collection_id: str = Form(...), file: UploadFile = File(...), identity=Depends(auth)
    ):
        content = await file.read(settings.max_upload_bytes + 1)
        return await anyio.to_thread.run_sync(
            lambda: upload_document(
                db, settings, identity, collection_id, file.filename or "document.txt", content
            )
        )

    @app.get("/api/documents/{document_id}")
    def document(document_id: str, identity=Depends(auth)):
        with db.session() as session:
            row = session.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant == identity.tenant,
                    Document.status != "deleted",
                )
            )
            if row is None:
                raise HTTPException(404, "Document not found")
            passages = list(
                session.scalars(
                    select(Chunk)
                    .where(Chunk.document_id == row.id, Chunk.tenant == identity.tenant)
                    .order_by(Chunk.ordinal)
                )
            )
            return {
                **document_dict(row),
                "passages": [
                    {"id": p.id, "text": p.text, "page": p.page, "heading": p.heading}
                    for p in passages
                ],
            }

    @app.get("/api/documents/{document_id}/download")
    def download(document_id: str, identity=Depends(auth)):
        with db.session() as session:
            row = session.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant == identity.tenant,
                    Document.status != "deleted",
                )
            )
            if row is None:
                raise HTTPException(404, "Document not found")
            return FileResponse(row.file_path, media_type=row.media_type, filename=row.filename)

    @app.delete("/api/documents/{document_id}")
    def delete_document(document_id: str, identity=Depends(auth)):
        remove_document(db, identity, document_id)
        return {"deleted": True}

    @app.post("/api/documents/{document_id}/retry")
    def retry(document_id: str, identity=Depends(auth)):
        identity.require_editor()
        with db.session() as session:
            row = session.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant == identity.tenant,
                    Document.status == "failed",
                )
            )
            if row is None:
                raise HTTPException(409, "Only failed documents can be retried")
            row.status, row.error = "queued", ""
            session.add(Job(tenant=identity.tenant, kind="index", entity_id=document_id))
        return {"queued": True}

    @app.get("/api/conversations")
    def conversations(identity=Depends(auth)):
        with db.session() as session:
            return [
                {"id": row.id, "title": row.title, "updated_at": row.updated_at}
                for row in session.scalars(
                    select(Conversation)
                    .where(
                        Conversation.tenant == identity.tenant, Conversation.user == identity.user
                    )
                    .order_by(Conversation.updated_at.desc())
                    .limit(100)
                )
            ]

    @app.post("/api/documents/{document_id}/reindex")
    def reindex(document_id: str, identity=Depends(auth)):
        identity.require_editor()
        with db.session() as session:
            row = session.scalar(
                select(Document).where(
                    Document.id == document_id,
                    Document.tenant == identity.tenant,
                    Document.status.in_(["ready", "failed"]),
                )
            )
            if row is None:
                raise HTTPException(409, "Choose a ready or failed source to reindex")
            row.status, row.error = "queued", ""
            session.add(Job(tenant=identity.tenant, kind="index", entity_id=document_id))
            session.add(
                Audit(
                    tenant=identity.tenant,
                    actor=identity.user,
                    action="document.reindex",
                    entity_id=document_id,
                )
            )
        return {"queued": True}

    @app.post("/api/conversations", status_code=201)
    def new_conversation(body: ConversationBody, identity=Depends(auth)):
        with db.session() as session:
            row = Conversation(tenant=identity.tenant, user=identity.user, title=body.title)
            session.add(row)
            session.flush()
            return {"id": row.id, "title": row.title, "updated_at": row.updated_at}

    @app.get("/api/conversations/{conversation_id}/messages")
    def messages(conversation_id: str, identity=Depends(auth)):
        with db.session() as session:
            conversation_for(session, identity, conversation_id)
            return [
                message_dict(session, row)
                for row in session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at)
                )
            ]

    @app.delete("/api/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str, identity=Depends(auth)):
        with db.session() as session:
            row = conversation_for(session, identity, conversation_id)
            if session.scalar(
                select(Message.id).where(
                    Message.conversation_id == conversation_id, Message.state == "generating"
                )
            ):
                raise HTTPException(409, "Stop the active answer before deleting this conversation")
            session.execute(delete(Message).where(Message.conversation_id == conversation_id))
            session.delete(row)
        return {"deleted": True}

    @app.post("/api/conversations/{conversation_id}/messages")
    async def answer(
        conversation_id: str, body: ChatBody, request: Request, identity=Depends(auth)
    ):
        if not body.question.strip():
            raise HTTPException(422, "Question cannot be blank")
        with db.session() as session:
            for collection_id in body.collection_ids:
                collection_for(session, identity, collection_id)
        iterator = await anyio.to_thread.run_sync(
            lambda: iter(begin_chat(db, runtime, identity, conversation_id, body))
        )

        async def send_events():
            try:
                while not await request.is_disconnected():
                    piece = await anyio.to_thread.run_sync(lambda: next(iterator, None))
                    if piece is None:
                        break
                    yield piece
            finally:
                if hasattr(iterator, "close"):
                    with anyio.CancelScope(shield=True):
                        await anyio.to_thread.run_sync(iterator.close)

        return StreamingResponse(
            send_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.patch("/api/messages/{message_id}/feedback")
    def feedback(message_id: str, body: FeedbackBody, identity=Depends(auth)):
        with db.session() as session:
            row = session.scalar(
                select(Message)
                .join(Conversation)
                .where(
                    Message.id == message_id,
                    Message.role == "assistant",
                    Conversation.tenant == identity.tenant,
                    Conversation.user == identity.user,
                )
            )
            if row is None:
                raise HTTPException(404, "Answer not found")
            row.feedback = body.value
        return {"feedback": body.value}

    @app.get("/api/experiments")
    def experiments(identity=Depends(auth)):
        with db.session() as session:
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "kind": row.kind,
                    "created_at": row.created_at,
                    "report": row.report,
                }
                for row in session.scalars(
                    select(Experiment)
                    .where(Experiment.tenant == identity.tenant)
                    .order_by(Experiment.created_at.desc())
                    .limit(50)
                )
            ]

    @app.get("/api/training/dataset")
    def training_dataset(identity=Depends(auth)):
        identity.require_admin()
        path = settings.data_dir / "training/train.jsonl"
        if not path.exists():
            raise HTTPException(404, "Create the original training fixture with the dataset script")
        return FileResponse(
            path, media_type="application/x-ndjson", filename="atlas-grounding-train.jsonl"
        )

    @app.get("/api/training/summary")
    def training_summary(identity=Depends(auth)):
        counts = {}
        for name in ("train", "validation", "test"):
            path = settings.data_dir / f"training/{name}.jsonl"
            counts[name] = (
                len([line for line in path.read_text().splitlines() if line.strip()])
                if path.exists()
                else 0
            )
        return {
            "counts": counts,
            "method": "Response-only LoRA / optional NF4 QLoRA",
            "base_model": settings.model_id,
            "adapter_loaded": runtime.ready and runtime.generator.has_adapter,
            "command": "python -m atlas_rag.training --steps 64 --grad-accum 1",
            "purpose": "Grounded answers, valid citations, and evidence-based abstention",
            "data_provenance": "Original synthetic policy scenarios; separate scenario groups for each split",
        }

    @app.get("/api/audit")
    def audit(identity=Depends(auth)):
        identity.require_admin()
        with db.session() as session:
            return [
                {
                    "action": row.action,
                    "actor": row.actor,
                    "entity_id": row.entity_id,
                    "created_at": row.created_at,
                }
                for row in session.scalars(
                    select(Audit)
                    .where(Audit.tenant == identity.tenant)
                    .order_by(Audit.created_at.desc())
                    .limit(100)
                )
            ]

    web = Path(__file__).parent / "web"
    if (web / "assets").exists():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        if not (web / "index.html").exists():
            return JSONResponse(
                {"detail": "Build the frontend: cd frontend && npm ci && npm run build"},
                status_code=503,
            )
        return FileResponse(web / "index.html")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(web / "favicon.svg", media_type="image/svg+xml")

    return app
