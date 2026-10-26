# Workspace role guide

Administrators manage membership, approve role changes, and review configuration. Editors upload, organize, and remove knowledge sources. Viewers can read authorized sources and ask the assistant questions. Editors and viewers cannot approve their own promotion to administrator.

Workspace identity is established by a verified authentication token. The workspace identifier in an untrusted request body must never override the verified identity. Conversation history is private to the authenticated user within their workspace.

Removing a knowledge source revokes it from new retrieval immediately. Answers that were already generated remain in their conversations until those conversations are deleted. A source reference to a removed document should indicate that the original source is unavailable.
