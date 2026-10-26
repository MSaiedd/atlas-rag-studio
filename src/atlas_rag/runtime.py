"""Model lifecycle and a lease-based durable ingestion worker."""

import logging
import threading
import time

from sqlalchemy import select, update

from .database import Document, Job
from .documents import cleanup_document, index_document
from .generation import CompatibleGenerator, LocalGenerator
from .retrieval import NeuralRetrieval, VectorIndex

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings, db, encoder=None, vectors=None, generator=None):
        self.settings, self.db = settings, db
        self.encoder, self.vectors, self.generator = encoder, vectors, generator
        self.ready = all(value is not None for value in (encoder, vectors, generator))
        self.error = ""
        self.stopping = threading.Event()
        self.generation_slots = threading.BoundedSemaphore(settings.max_pending_generations)
        self.threads = []

    def start(self):
        if not self.ready and self.settings.model_loading:
            thread = threading.Thread(target=self._initialize, daemon=True, name="atlas-models")
            self.threads.append(thread)
            thread.start()
        if self.settings.worker_enabled:
            thread = threading.Thread(target=self._worker, daemon=True, name="atlas-indexer")
            self.threads.append(thread)
            thread.start()

    def _initialize(self):
        try:
            self.encoder = NeuralRetrieval(self.settings)
            self.vectors = VectorIndex(
                self.settings, self.encoder.dimension, self.encoder.fingerprint
            )
            self.generator = (
                LocalGenerator(self.settings)
                if self.settings.llm_backend == "local"
                else CompatibleGenerator(self.settings)
            )
            self.ready = True
            logger.info("Atlas retrieval and generation models are ready")
        except Exception:
            logger.exception("Atlas model initialization failed")
            self.error = "Model initialization failed. Check server logs and model cache settings."

    def claim_job(self):
        now = time.time()
        with self.db.session() as session:
            # Expired leases are retried; deterministic chunk IDs make interrupted upserts safe.
            session.execute(
                update(Job)
                .where(Job.state == "running", Job.lease_until < now)
                .values(state="queued")
            )
            row = session.scalar(
                select(Job)
                .where(Job.state == "queued")
                .order_by(Job.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                return None
            claimed = session.execute(
                update(Job)
                .where(Job.id == row.id, Job.state == "queued")
                .values(state="running", attempts=Job.attempts + 1, lease_until=now + 600)
            )
            if not claimed.rowcount:
                return None
            return {
                "id": row.id,
                "kind": row.kind,
                "entity_id": row.entity_id,
                "attempts": row.attempts + 1,
            }

    def process_one(self):
        if not self.ready:
            return False
        job = self.claim_job()
        if job is None:
            return False
        try:
            if job["kind"] == "index":
                index_document(self.db, self.settings, self.vectors, self.encoder, job["entity_id"])
            elif job["kind"] == "delete":
                cleanup_document(self.db, self.vectors, job["entity_id"])
            else:
                raise ValueError("Unknown job kind")
            with self.db.session() as session:
                session.get(Job, job["id"]).state = "complete"
        except Exception as error:
            logger.exception("Atlas indexing job failed: %s", job["id"])
            with self.db.session() as session:
                row = session.get(Job, job["id"])
                row.state = "failed"
                row.error = str(error)[:500]
                document = session.get(Document, job["entity_id"])
                if document and document.status != "deleted":
                    document.status, document.error = "failed", str(error)[:500]
        return True

    def _worker(self):
        while not self.stopping.wait(0.5):
            try:
                self.process_one()
            except Exception:
                logger.exception("Index worker could not acquire a job")

    def close(self):
        self.stopping.set()
        for thread in self.threads:
            thread.join(timeout=5)
        if self.vectors:
            self.vectors.close()
