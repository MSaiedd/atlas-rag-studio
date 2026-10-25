# Security and deployment boundaries

These are portfolio applications validated locally. Do not expose them publicly unchanged.
Bearer tokens are static development identities, not a complete account system. Rotate tokens
by changing server configuration and restarting. Use HTTPS, an identity gateway, request size
limits, rate limiting, monitoring, and restricted network access for a public deployment.
Browser tokens are held only in page memory. Never put tokens in URLs or query parameters.
SQLite persists state for a single server; use managed storage and tested backups before scaling.
Model outputs are untrusted data. Application code enforces authorization and sensitive writes.
Locally running Ollama may send inputs elsewhere if configured with a remote URL; choose trusted servers.
No production integrations, external credentials, or real customer datasets are bundled.

Report a vulnerability privately through the repository owner's GitHub profile contact methods.
Do not post secrets or personal information in public issues.
