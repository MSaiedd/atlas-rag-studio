# Security boundaries

Atlas is locally validated portfolio software. Public operation requires configured identity,
network controls, resource sizing and live operational validation.

## Identity

Local mode is an explicit shared workspace for one computer. The normal listener is 127.0.0.1;
allowed hostnames and client networks are checked. The compose listener is also loopback-only,
with its local Docker bridge range explicitly trusted. Never expose local-auth mode publicly.

Hosted mode verifies signed OIDC JWTs against a configured HTTPS JWKS endpoint, issuer, audience,
expiry, subject and workspace claim. Roles must be a list of recognized names. Access tokens stay
in browser memory. A complete identity-provider login/PKCE flow is not bundled.

Workspace identity cannot be supplied in request payloads. Sources are shared within a workspace;
conversation history is scoped to its user. Vector results are filtered by workspace and then
rechecked against active relational metadata before any passage enters a model prompt.

## Files and model output

Uploads have bounded size, extracted text, pages and passage counts. Files use generated storage
paths; original filenames never select filesystem paths. Linux PDF parsing runs in a separate
process with memory and CPU limits and a wall timeout. OCR and other formats are not supported.

Documents and model output are untrusted text. React renders text and citation components without
raw HTML. Content Security Policy and same-origin write checks apply. Provider credentials remain
server-side. An external configured model provider receives the supplied evidence and conversation
text; evaluate privacy requirements before using one.

Citation checks validate source IDs and paragraph-level reference presence. They do not prove
claim-level support and do not eliminate prompt injection. The generator has no business-action
tools. A structurally valid answer can still be wrong and needs task-specific evaluation.

## Persistence and retention

Deletion revokes retrieval before asynchronous vector/file cleanup. Historic answers remain in
conversations until those conversations are removed. Historic source excerpts are not duplicated
in message storage; they are hydrated only while the original source remains active.

Only load adapter/model artifacts from trusted operators. Training runs are executed outside the
serving process. Never deserialize arbitrary user-supplied model files. Runtime data, real tokens,
uploads and model caches are ignored by Git.

## Production gates

Use TLS, explicit hostnames, real OIDC integration, rate limiting, monitoring, tested backups and
restore procedures. Deploy private PostgreSQL and authenticated private Qdrant. Validate parser
limits, worker recovery, model quality, sustained traffic and dependency updates in your environment.
No live enterprise identity provider, public hosting, high-traffic rollout or GPU QLoRA run is claimed.

Report vulnerabilities through the repository owner's GitHub contact methods. Do not publish
credentials or customer data in an issue.
