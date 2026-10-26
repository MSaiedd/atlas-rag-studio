"""Rebuild a workspace's active sources after an embedding/index configuration change."""

from sqlalchemy import select

from .config import Settings
from .database import Database, Document, Job


def main():
    settings = Settings()
    db = Database(settings.database_url)
    with db.session() as session:
        rows = list(
            session.scalars(
                select(Document).where(
                    Document.tenant == settings.local_tenant,
                    Document.status.in_(["ready", "failed"]),
                )
            )
        )
        for row in rows:
            row.status, row.error = "queued", ""
            session.add(Job(tenant=row.tenant, kind="index", entity_id=row.id))
        print(f"Queued {len(rows)} sources for workspace {settings.local_tenant}")
    db.engine.dispose()


if __name__ == "__main__":
    main()
