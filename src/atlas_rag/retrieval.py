"""Multilingual dense + native lexical retrieval, rank fusion and learned reranking."""

import hashlib
import re
import threading
import time
from dataclasses import dataclass, field

from qdrant_client import QdrantClient, models
from sqlalchemy import bindparam, select, text

from .database import Chunk, Document


class NeuralRetrieval:
    def __init__(self, settings):
        import torch
        from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(settings.cpu_threads)
        kwargs = {"local_files_only": settings.offline}
        self.torch = torch
        self.lock = threading.Lock()
        self.tokenizer = AutoTokenizer.from_pretrained(
            settings.embedding_model, revision=settings.embedding_revision, **kwargs
        )
        self.model = AutoModel.from_pretrained(
            settings.embedding_model, revision=settings.embedding_revision, **kwargs
        ).eval()
        self.dimension = self.model.config.hidden_size
        self.revision = (
            getattr(self.model.config, "_commit_hash", None) or settings.embedding_revision
        )
        self.rerank_tokenizer = AutoTokenizer.from_pretrained(
            settings.reranker_model, revision=settings.reranker_revision, **kwargs
        )
        self.reranker = AutoModelForSequenceClassification.from_pretrained(
            settings.reranker_model, revision=settings.reranker_revision, **kwargs
        ).eval()
        self.reranker_revision = (
            getattr(self.reranker.config, "_commit_hash", None) or settings.reranker_revision
        )
        self.fingerprint = hashlib.sha256(
            f"{settings.embedding_model}:{self.revision}:{self.dimension}".encode()
        ).hexdigest()[:12]

    def _encode(self, texts):
        with self.lock, self.torch.inference_mode():
            inputs = self.tokenizer(
                texts, padding=True, truncation=True, max_length=512, return_tensors="pt"
            )
            hidden = self.model(**inputs).last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            return self.torch.nn.functional.normalize(pooled, dim=1).numpy().tolist()

    def encode_documents(self, texts):
        # E5 requires these prefixes for Arabic as well as English.
        return self._encode(["passage: " + value for value in texts])

    def encode_query(self, question):
        return self._encode(["query: " + question])[0]

    def rerank(self, question, passages):
        if not passages:
            return []
        with self.lock, self.torch.inference_mode():
            batch = self.rerank_tokenizer(
                [question] * len(passages),
                passages,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            return self.reranker(**batch).logits[:, 0].float().tolist()


class VectorIndex:
    def __init__(self, settings, dimension, fingerprint):
        self.client = (
            QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key
                else None,
                timeout=20,
            )
            if settings.qdrant_url
            else QdrantClient(path=str(settings.data_dir / "qdrant"))
        )
        self.name = f"atlas_{fingerprint}"
        self.lock = threading.RLock()
        if not self.client.collection_exists(self.name):
            self.client.create_collection(
                self.name,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
            )
            if settings.qdrant_url:
                for name in ("tenant", "collection_id", "document_id"):
                    self.client.create_payload_index(
                        self.name, name, models.PayloadSchemaType.KEYWORD
                    )

    @staticmethod
    def scope(tenant, collection_ids=None, document_id=None):
        must = [models.FieldCondition(key="tenant", match=models.MatchValue(value=tenant))]
        if collection_ids:
            must.append(
                models.FieldCondition(
                    key="collection_id", match=models.MatchAny(any=collection_ids)
                )
            )
        if document_id:
            must.append(
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
            )
        return models.Filter(must=must)

    def upsert(self, chunks, embeddings):
        points = [
            models.PointStruct(
                id=c.id,
                vector=vector,
                payload={
                    "tenant": c.tenant,
                    "collection_id": c.collection_id,
                    "document_id": c.document_id,
                },
            )
            for c, vector in zip(chunks, embeddings, strict=True)
        ]
        with self.lock:
            self.client.upsert(self.name, points, wait=True)

    def search(self, tenant, vector, collection_ids, limit):
        with self.lock:
            result = self.client.query_points(
                self.name,
                query=vector,
                query_filter=self.scope(tenant, collection_ids),
                limit=limit,
                with_payload=False,
            ).points
        return [(str(point.id), float(point.score)) for point in result]

    def delete_document(self, tenant, document_id):
        with self.lock:
            self.client.delete(
                self.name,
                models.FilterSelector(filter=self.scope(tenant, document_id=document_id)),
                wait=True,
            )

    def close(self):
        self.client.close()


@dataclass
class Passage:
    id: str
    document_id: str
    collection_id: str
    title: str
    filename: str
    text: str
    page: int
    heading: str
    dense_score: float = 0.0
    lexical_score: float = 0.0
    fusion_score: float = 0.0
    rerank_score: float = 0.0


@dataclass
class RetrievalResult:
    passages: list[Passage] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    query: str = ""


def lexical_search(db, tenant, question, collection_ids, limit):
    terms = re.findall(r"[^\W_]+", question.casefold(), re.UNICODE)[:40]
    if not terms:
        return []
    scope = " AND c.collection_id IN :collections" if collection_ids else ""
    if db.sqlite:
        sql = f"""SELECT c.id, bm25(chunk_fts) AS score FROM chunk_fts
            JOIN chunks c ON c.id=chunk_fts.chunk_id JOIN documents d ON d.id=c.document_id
            WHERE chunk_fts MATCH :query AND c.tenant=:tenant AND d.tenant=:tenant
            AND d.status='ready' {scope} ORDER BY score LIMIT :limit"""
        query = " OR ".join('"' + term + '"' for term in terms)
    else:
        sql = f"""SELECT c.id, ts_rank_cd(to_tsvector('simple', c.text),
            to_tsquery('simple', :query)) AS score FROM chunks c
            JOIN documents d ON d.id=c.document_id WHERE c.tenant=:tenant AND d.tenant=:tenant
            AND d.status='ready' AND to_tsvector('simple', c.text) @@ to_tsquery('simple', :query)
            {scope} ORDER BY score DESC LIMIT :limit"""
        query = " | ".join("'" + term.replace("'", "") + "'" for term in terms)
    statement = text(sql)
    if collection_ids:
        statement = statement.bindparams(bindparam("collections", expanding=True))
    with db.session() as session:
        values = {"query": query, "tenant": tenant, "limit": limit}
        if collection_ids:
            values["collections"] = collection_ids
        rows = session.execute(statement, values).all()
    return [(row.id, -float(row.score) if db.sqlite else float(row.score)) for row in rows]


def retrieve(
    db, settings, vectors, encoder, identity, question, collection_ids=None, method="reranked"
):
    started = time.perf_counter()
    lexical = lexical_search(
        db, identity.tenant, question, collection_ids, settings.retrieval_candidates
    )
    lexical_ms = (time.perf_counter() - started) * 1000
    dense = []
    if method != "lexical":
        dense = vectors.search(
            identity.tenant,
            encoder.encode_query(question),
            collection_ids,
            settings.retrieval_candidates,
        )
    dense_ms = (time.perf_counter() - started) * 1000 - lexical_ms
    ranks = {}
    signals = (
        [lexical] if method == "lexical" else [dense] if method == "dense" else [dense, lexical]
    )
    for signal in signals:
        for rank, (chunk_id, _) in enumerate(signal, 1):
            ranks[chunk_id] = ranks.get(chunk_id, 0.0) + 1 / (60 + rank)
    ordered = sorted(ranks, key=lambda key: (-ranks[key], key))[: settings.retrieval_candidates]
    with db.session() as session:
        statement = (
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Chunk.id.in_(ordered),
                Chunk.tenant == identity.tenant,
                Document.tenant == identity.tenant,
                Document.status == "ready",
            )
        )
        if collection_ids:
            statement = statement.where(Chunk.collection_id.in_(collection_ids))
        rows = {chunk.id: (chunk, document) for chunk, document in session.execute(statement)}
        passages = []
        for key in ordered:
            if key not in rows:
                continue
            chunk, document = rows[key]
            passages.append(
                Passage(
                    chunk.id,
                    chunk.document_id,
                    chunk.collection_id,
                    document.title,
                    document.filename,
                    chunk.text,
                    chunk.page,
                    chunk.heading,
                    dict(dense).get(key, 0.0),
                    dict(lexical).get(key, 0.0),
                    ranks[key],
                )
            )
    rerank_started = time.perf_counter()
    if method == "reranked" and passages:
        scores = encoder.rerank(question, [p.text for p in passages])
        for passage, score in zip(passages, scores, strict=True):
            passage.rerank_score = float(score)
        passages.sort(key=lambda p: (-p.rerank_score, -p.fusion_score))
    candidates = [
        {
            "chunk_id": p.id,
            "title": p.title,
            "dense_score": round(p.dense_score, 4),
            "lexical_score": round(p.lexical_score, 4),
            "fusion_score": round(p.fusion_score, 5),
            "rerank_score": round(p.rerank_score, 4),
        }
        for p in passages
    ]
    if method == "reranked":
        passages = [p for p in passages if p.rerank_score >= settings.min_rerank_score]
    return RetrievalResult(
        passages[: settings.retrieval_top_k],
        candidates,
        {
            "lexical_ms": round(lexical_ms, 2),
            "dense_ms": round(dense_ms, 2),
            "rerank_ms": round((time.perf_counter() - rerank_started) * 1000, 2),
            "retrieval_ms": round((time.perf_counter() - started) * 1000, 2),
        },
        question,
    )
