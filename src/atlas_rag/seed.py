"""Idempotently enqueue original fictional workspace documents."""

import json

from sqlalchemy import select

from .auth import Identity
from .config import Settings
from .database import Collection, Database
from .documents import upload_document


def main():
    settings = Settings()
    db = Database(settings.database_url)
    identity = Identity(settings.local_tenant, "local-owner", "admin")
    directory = settings.data_dir / "examples"
    for group in json.loads((directory / "manifest.json").read_text()):
        with db.session() as session:
            collection = session.scalar(
                select(Collection).where(
                    Collection.tenant == identity.tenant, Collection.name == group["name"]
                )
            )
            if collection is None:
                collection = Collection(
                    tenant=identity.tenant,
                    name=group["name"],
                    description=group["description"],
                    color=group["color"],
                )
                session.add(collection)
                session.flush()
            collection_id = collection.id
        for filename in group["files"]:
            result = upload_document(
                db, settings, identity, collection_id, filename, (directory / filename).read_bytes()
            )
            print(filename, "already present" if result["duplicate"] else "queued")
    db.engine.dispose()


if __name__ == "__main__":
    main()
