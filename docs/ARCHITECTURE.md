# Architecture decisions

- The commerce system is a persistent simulation. No payment credentials or live refunds are used.
- The deterministic baseline provides a repeatable control for the optional model/tool loop.
- Tools bind account/order scope at the server. The model receives no approval capability.
- Refund requests and decisions use immediate SQLite transactions, making concurrent decisions serializable.
- A unique order/refund relation prevents duplicate refund effects. Identical final decisions replay safely.
- Approval rechecks policy inside the same transaction as the order-state change.
- Failed model calls persist a failed ticket; a pending refund can survive a failure and must be reviewed.
- The audit log is transactional application evidence, not an immutable external compliance ledger.
- A real commerce integration needs payment-provider idempotency, webhook reconciliation, and a durable job queue.

Evaluate the model-driven path separately from the baseline: measure task success, unauthorized writes,
tool-call correctness, escalation accuracy, latency, and cost on reviewed scenarios. Do not infer
live-model success from deterministic workflow tests or mocked provider responses.
