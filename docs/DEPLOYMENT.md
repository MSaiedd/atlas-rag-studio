# Deployment and recovery

## Local computer

Bind Uvicorn to `127.0.0.1`, use local auth, and leave the trusted client networks at loopback.
Model weights download once into the Hugging Face hub cache. Adapter weights live under
`artifacts/grounded-lora`; source files, relational state and local vectors live under `data`.
These private runtime paths are excluded from Git. Use one Uvicorn process with embedded Qdrant.

## Compose topology

`compose.yaml` supplies PostgreSQL 17.11 and authenticated Qdrant 1.20.0. Fresh passwords and API keys
are mandatory. Only the app publishes a host port, bound to `127.0.0.1`. Named volumes persist state.
The app trusts the Docker bridge client range only for this local, loopback-published configuration.
Never publish local-auth mode on a public interface or behind a public reverse proxy.

The image builds the React frontend, installs CPU PyTorch, and runs as an unprivileged user.
Its liveness check reports process availability; `/ready` returns 503 until neural components load.
Do not route model requests merely because `/health` responds. Initial model downloads can take time.

The upload/parser limit is 10 MB / 200 PDF pages / 150,000 extracted characters / 256 passages.
Match reverse-proxy request limits. Preserve streaming responses and disable proxy buffering.

## Hosted identity

Set `ATLAS_AUTH_MODE=oidc` and configure HTTPS JWKS, issuer, audience, and the public hostname.
Verified JWTs must contain `sub`, `workspace_id`, `iat`, and `exp`; optional `roles` is a list of
`admin`, `editor`, or `viewer`. JWT signature, issuer, audience and expiry are checked. The browser
accepts an organization's access token in memory; a full OIDC login/PKCE redirect flow is not bundled.

TLS termination, rate limiting, request tracing, alerting, secret rotation and account lifecycle
integration are deployment responsibilities. Real identity-provider integration remains a live gate.

Configure the proxy to preserve the public Host and send the original scheme/client headers.
Set Uvicorn `FORWARDED_ALLOW_IPS` to the specific trusted proxy addresses when that proxy is
not on loopback. Restrict direct backend access; trusting arbitrary forwarded headers would
undermine client-address checks. The public Origin must match the reconstructed request URL
for write requests to pass the same-origin check.

## Larger model serving

Use `ATLAS_LLM_BACKEND=compatible` for a private vLLM/TGI-compatible streaming endpoint.
Configure base and adapter model names explicitly. Provider keys remain in server environment
settings. The runtime sends bounded evidence and conversation text to that configured provider.
Validate privacy requirements before choosing an external provider.

CPU model serving and GPU inference fleets have different capacity. No high-traffic GPU capacity
claim follows from this project's CPU run. Benchmark the actual model, context distribution,
request concurrency, TTFT, p95/p99 complete-response time and failure behavior before rollout.

## Backup, restore and upgrade

Back up PostgreSQL, source uploads, adapter manifests/weights and Qdrant snapshots as a coordinated
generation. Record the embedding model revision. Restored orphan vectors are filtered through
relational visibility, but missing vectors require reindexing original sources.

Practice restoration in an isolated workspace and verify document counts, vector dimension,
workspace isolation, retrieval, source deletion, conversation history and model revision.
The repository's checks do not establish that your live backups have been restored successfully.

The old SupportPilot database is not migrated: Atlas intentionally uses `data/atlas.db`.
Preserve the previous release tag for source rollback. For future Atlas schema changes, introduce
and test explicit versioned migrations before upgrading a live database.
