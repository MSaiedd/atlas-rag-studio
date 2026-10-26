"""Write original, fictional Northstar workspace documents used by the local walkthrough."""

import json
from pathlib import Path

DOCUMENTS = {
    "Product & billing": {
        "color": "indigo",
        "description": "Plans, subscriptions, and billing policies",
        "documents": {
            "annual-subscription-policy.md": """# Annual subscription policy

## Standard refund window
Northstar accepts refund requests for unused annual subscriptions within 14 calendar days of purchase. A support operator must verify account ownership, confirm the purchase date, and approve the request. A refund is never automatically approved by a chatbot.

## Contract exceptions
Enterprise customers may have a different refund window only when an executed enterprise agreement explicitly overrides the standard policy. The account manager must confirm the relevant contract clause in writing. A support agent must not invent an exception or promise approval before that confirmation.

## Monthly plans
Monthly subscriptions can be cancelled before their next renewal. The current monthly billing period is not refundable under the standard policy. Unused annual plans and monthly cancellations follow different procedures.

## Required information
Ask for the order reference and the account email. Never ask a customer to provide a password, verification code, or full payment card number.
""",
            "refund-processing.md": """# Refund processing and payment review

## Processing time
After a support operator approves a Northstar refund, payment processing takes five business days. The clock starts at approval, not when the customer opens a ticket. Weekends and public holidays are excluded. A customer should not be promised an exact bank posting date.

## Duplicate charges
For a possible duplicate charge, ask for the order reference and the dates and amounts of the two charges. The billing team compares payment-provider transaction IDs. A pending bank authorization may differ from a settled charge, so a support agent must not assume both entries represent completed payments.

## Follow-up
If five business days have passed since approval, the billing team requests a payment-provider trace. All follow-up should be linked to the original refund request. These fictional policies do not execute a real payment.
""",
            "plan-entitlements.md": """# Northstar plan entitlements

Starter workspaces include five members and one knowledge collection. Team workspaces include 50 members and ten collections. Enterprise workspace limits are defined in the executed contract. Usage beyond a contracted limit requires explicit approval before a plan change.

Administrators can view current membership and collection usage in workspace settings. An editor can maintain documents but cannot change the subscription or approve a charge. Viewers can read available knowledge and ask questions.

There is no documented Black Friday discount in this knowledge base. Commercial discounts must be verified with the account owner rather than inferred from historical campaigns.
""",
        },
    },
    "Engineering": {
        "color": "teal",
        "description": "API behavior, reliability, and release practices",
        "documents": {
            "api-rate-limits.md": """# API rate limits and retries

## Workspace quota
The fictional Northstar API permits 600 requests per minute per workspace, with a short burst limit of 30 requests. A request above the limit receives HTTP 429. The response includes a Retry-After header in seconds.

## Retry behavior
When a request receives 429, honor Retry-After before sending another request. When the header is missing, use exponential backoff with full jitter: initial delays of approximately 1, 2, 4, and 8 seconds, capped at 30 seconds. Stop after five attempts and surface a recoverable error to the caller. Retrying immediately in a tight loop increases contention.

## Safe writes
Only retry a write when it carries an idempotency key or the endpoint documentation explicitly states the operation is idempotent. Authentication failures such as HTTP 401 require credential repair, not blind retries.
""",
            "idempotency-and-webhooks.md": """# Idempotency and webhook delivery

Write requests that create payment reviews or refund requests require an Idempotency-Key header. Store the key with the operation result for 72 hours. Reusing the same key with a different request body returns HTTP 409. Replaying the same request returns the original operation result.

Webhook events can be delivered more than once or arrive out of order. Consumers must verify the webhook signature, deduplicate by event ID, and reconcile the event against current durable state. An acknowledgment means the event was accepted for processing, not that a payment operation finished.

Do not treat a model-generated statement as proof that a downstream API action succeeded. The durable operation record and provider acknowledgment determine the actual result.
""",
            "release-checklist.md": """# Release readiness checklist

Every release requires passing automated checks, a tested database migration, an operator-visible rollback plan, and a recorded build identifier. Deploy to staging before production and run representative browser and API checks.

Use a small canary before broad rollout. Observe p95 request latency, error rate, queue age, and database saturation. Pause rollout when errors exceed the agreed service target or when persistent data integrity checks fail.

Schema changes should remain compatible with the previous application version until rollback is no longer required. A successful local test is not evidence of a successful public deployment.
""",
        },
    },
    "Security & access": {
        "color": "rose",
        "description": "Identity, account protection, and data handling",
        "documents": {
            "compromised-account-runbook.md": """# Compromised account runbook

## Immediate response
When an employee reports a compromised account, revoke active sessions immediately and notify the security team. Verify the employee through the organization's approved recovery channel. Rotate the password and any exposed API tokens after ownership is established.

## Recovery
Re-enroll multi-factor authentication if its factors may be exposed. Review recent sign-ins, privilege changes, and data exports. Preserve relevant audit records and open a security incident. Active account compromise is priority P1 and must be acknowledged within 15 minutes.

## Communication boundaries
Support staff must never ask for a password or one-time verification code. A model must not mark an account recovered or claim that sessions were revoked unless an authorized system reports success.
""",
            "workspace-roles.md": """# Workspace role guide

Administrators manage membership, approve role changes, and review configuration. Editors upload, organize, and remove knowledge sources. Viewers can read authorized sources and ask the assistant questions. Editors and viewers cannot approve their own promotion to administrator.

Workspace identity is established by a verified authentication token. The workspace identifier in an untrusted request body must never override the verified identity. Conversation history is private to the authenticated user within their workspace.

Removing a knowledge source revokes it from new retrieval immediately. Answers that were already generated remain in their conversations until those conversations are deleted. A source reference to a removed document should indicate that the original source is unavailable.
""",
            "data-retention.md": """# Audit retention and backup policy

Northstar retains operational audit events for 90 days. Encrypted database backups are retained for 30 days. The operations team must test a restore every month and record both the restore result and the time required.

Restoring a database requires checking the corresponding vector index generation. Relational metadata is the authorization source of truth; orphaned vector entries must not make deleted or unauthorized source text retrievable.

Secrets must be supplied through the deployment environment or a secret manager. Never commit production credentials, identity tokens, or real customer documents to the public source repository.
""",
        },
    },
    "Support operations": {
        "color": "amber",
        "description": "Triage, escalation, and evidence-led answers",
        "documents": {
            "ticket-triage.md": """# Support triage guide

Priority P1 covers active account compromise and a confirmed widespread service outage. Acknowledge P1 within 15 minutes and involve the security or incident-response owner. Priority P2 includes unresolved billing discrepancies and blocked business workflows; acknowledge within four business hours. Priority P3 includes general product questions; acknowledge within one business day.

Classify the impact from verified facts rather than emotional wording alone. Ask a clarifying question when the impact is uncertain. A pending request must not be described as completed, and an unverified claim about payment or account access must be escalated for review.

Use evidence from the current knowledge collection. If the documents do not answer a question, say so instead of inventing a policy, employee contact, commercial promise, or service-level commitment.
""",
            "refund-review-workflow.md": """# Refund review workflow

First verify the customer's ownership of the order, then identify whether the purchase is an annual or monthly subscription. For an unused annual subscription, check whether the request is within the standard 14-calendar-day window. Contract exceptions need written account-manager confirmation.

An authorized support operator approves or rejects the request. Approval is a distinct action from requesting a refund. Once approved, the payment review process uses the original request ID and a stable idempotency key. Payment processing normally takes five business days after approval.

If the applicable policy or contract is missing, ask for clarification and escalate. Never claim that a refund was issued based only on a language model response.
""",
        },
    },
}


def create(root):
    directory = root / "data/examples"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, group in DOCUMENTS.items():
        files = []
        for filename, content in group["documents"].items():
            (directory / filename).write_text(content.strip() + "\n")
            files.append(filename)
        manifest.append(
            {
                "name": name,
                "description": group["description"],
                "color": group["color"],
                "files": files,
            }
        )
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Created", sum(len(group["files"]) for group in manifest), "original fictional documents")


if __name__ == "__main__":
    create(Path(__file__).resolve().parents[1])
