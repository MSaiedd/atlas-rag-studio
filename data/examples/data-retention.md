# Audit retention and backup policy

Northstar retains operational audit events for 90 days. Encrypted database backups are retained for 30 days. The operations team must test a restore every month and record both the restore result and the time required.

Restoring a database requires checking the corresponding vector index generation. Relational metadata is the authorization source of truth; orphaned vector entries must not make deleted or unauthorized source text retrievable.

Secrets must be supplied through the deployment environment or a secret manager. Never commit production credentials, identity tokens, or real customer documents to the public source repository.
