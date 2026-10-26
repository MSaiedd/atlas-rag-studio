"""Bounded file extraction, page-aware chunks and transactional ingestion records."""

import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .database import Audit, Chunk, Collection, Document, Job, new_id


def extract_pages(content: bytes, filename: str, max_characters: int):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("This file is not a valid PDF")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "atlas_rag.pdf_worker", str(max_characters)],
                input=content,
                capture_output=True,
                timeout=25,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("PDF parsing exceeded its time budget") from error
        if result.returncode:
            raise ValueError("PDF exceeded the parser resource budget")
        parsed = json.loads(result.stdout)
        if parsed.get("error"):
            raise ValueError(parsed["error"])
        return [(int(page), value) for page, value in parsed["pages"]]
    if suffix not in {".md", ".txt"}:
        raise ValueError("Supported formats are PDF, Markdown and UTF-8 text")
    value = content.decode("utf-8-sig")
    if not value.strip() or "\x00" in value:
        raise ValueError("Upload a non-empty UTF-8 text document")
    if len(value) > max_characters:
        raise ValueError("Document text exceeds this workspace's ingestion limit")
    return [(1, value)]


def split_pages(pages, size=1100, overlap=160):
    """Prefer paragraph boundaries and preserve the page and heading of each passage."""
    parts = []
    for page, value in pages:
        heading = ""
        for match in re.finditer(r"(?m)^#{1,3}\s+(.+)$", value):
            if match.start() == 0:
                heading = match.group(1)
                break
        start = 0
        while start < len(value):
            end = min(start + size, len(value))
            if end < len(value):
                boundary = value.rfind("\n\n", start + size // 2, end)
                if boundary > start:
                    end = boundary
            text_value = value[start:end].strip()
            if text_value:
                local_headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", value[:end])
                parts.append(
                    {
                        "text": text_value,
                        "page": page,
                        "heading": local_headings[-1] if local_headings else heading,
                        "token_estimate": max(1, len(text_value) // 3),
                    }
                )
            if end == len(value):
                break
            start = max(start + 1, end - overlap)
    return parts


def collection_for(session, identity, collection_id):
    row = session.scalar(
        select(Collection).where(
            Collection.id == collection_id, Collection.tenant == identity.tenant
        )
    )
    if row is None:
        raise HTTPException(404, "Knowledge collection not found")
    return row


def document_dict(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "collection_id",
            "title",
            "filename",
            "status",
            "bytes",
            "pages",
            "chunk_count",
            "error",
            "created_at",
            "updated_at",
        )
    }


def upload_document(db, settings, identity, collection_id, filename, content):
    identity.require_editor()
    filename = filename.replace("\\", "/").split("/")[-1][:240]
    if Path(filename).suffix.lower() not in {".pdf", ".md", ".txt"}:
        raise HTTPException(415, "Choose a PDF, Markdown or text file")
    if not content or len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "Files must be non-empty and no larger than 10 MB")
    digest = hashlib.sha256(content).hexdigest()
    with db.session() as session:
        collection_for(session, identity, collection_id)
        previous = session.scalar(
            select(Document).where(
                Document.tenant == identity.tenant,
                Document.collection_id == collection_id,
                Document.sha256 == digest,
                Document.status != "deleted",
            )
        )
        if previous:
            return {**document_dict(previous), "duplicate": True}
    document_id = new_id()
    directory = (
        settings.data_dir / "uploads" / hashlib.sha256(identity.tenant.encode()).hexdigest()[:16]
    )
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document_id}{Path(filename).suffix.lower()}"
    path.write_bytes(content)
    path.chmod(0o600)
    try:
        with db.session() as session:
            # Recheck collection ownership in the same transaction as the write.
            collection_for(session, identity, collection_id)
            row = Document(
                id=document_id,
                tenant=identity.tenant,
                collection_id=collection_id,
                title=Path(filename).stem.replace("-", " "),
                filename=filename,
                file_path=str(path.resolve()),
                sha256=digest,
                media_type="application/pdf" if filename.lower().endswith(".pdf") else "text/plain",
                bytes=len(content),
                status="queued",
            )
            session.add(row)
            session.add(Job(tenant=identity.tenant, kind="index", entity_id=document_id))
            session.add(
                Audit(
                    tenant=identity.tenant,
                    actor=identity.user,
                    action="document.uploaded",
                    entity_id=document_id,
                )
            )
            session.flush()
            return {**document_dict(row), "duplicate": False}
    except IntegrityError:
        path.unlink(missing_ok=True)
        # An identical upload can race us; return the winning record without another job.
        with db.session() as session:
            row = session.scalar(
                select(Document).where(
                    Document.tenant == identity.tenant,
                    Document.collection_id == collection_id,
                    Document.sha256 == digest,
                    Document.status != "deleted",
                )
            )
            if row:
                return {**document_dict(row), "duplicate": True}
        raise
    except Exception:
        path.unlink(missing_ok=True)
        raise


def index_document(db, settings, vectors, encoder, document_id):
    with db.session() as session:
        row = session.get(Document, document_id)
        if row is None or row.status == "deleted":
            return
        row.status = "indexing"
        row.error = ""
        values = {
            key: getattr(row, key)
            for key in ("tenant", "collection_id", "filename", "file_path", "sha256")
        }
    pages = extract_pages(
        Path(values["file_path"]).read_bytes(), values["filename"], settings.max_document_characters
    )
    parts = split_pages(pages)
    if not parts or len(parts) > settings.max_chunks:
        raise ValueError(f"Documents must contain 1–{settings.max_chunks} passages")
    chunks = [
        Chunk(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"atlas:{document_id}:{values['sha256']}:{i}")),
            tenant=values["tenant"],
            collection_id=values["collection_id"],
            document_id=document_id,
            ordinal=i,
            **part,
        )
        for i, part in enumerate(parts)
    ]
    for start in range(0, len(chunks), 16):
        batch = chunks[start : start + 16]
        embeddings = encoder.encode_documents([c.text for c in batch])
        vectors.upsert(batch, embeddings)
    with db.session() as session:
        row = session.get(Document, document_id)
        if row is None or row.status == "deleted":
            # Deletion wins a race with embedding; no stale result becomes visible.
            vectors.delete_document(values["tenant"], document_id)
            return
        previous = list(session.scalars(select(Chunk.id).where(Chunk.document_id == document_id)))
        db.delete_lexical(session, previous)
        session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        session.add_all(chunks)
        session.flush()
        for chunk in chunks:
            db.index_lexical(session, chunk)
        row.status, row.pages, row.chunk_count = "ready", max(p[0] for p in pages), len(chunks)
        row.updated_at = time.time()


def remove_document(db, identity, document_id):
    identity.require_editor()
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
        # Revoke retrieval immediately, even when the vector service is temporarily unavailable.
        row.status, row.updated_at = "deleted", time.time()
        session.add(Job(tenant=identity.tenant, kind="delete", entity_id=document_id))
        session.add(
            Audit(
                tenant=identity.tenant,
                actor=identity.user,
                action="document.deleted",
                entity_id=document_id,
            )
        )


def cleanup_document(db, vectors, document_id):
    with db.session() as session:
        row = session.get(Document, document_id)
        if row is None or row.status != "deleted":
            return
        vectors.delete_document(row.tenant, document_id)
        ids = list(session.scalars(select(Chunk.id).where(Chunk.document_id == document_id)))
        db.delete_lexical(session, ids)
        session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        Path(row.file_path).unlink(missing_ok=True)
