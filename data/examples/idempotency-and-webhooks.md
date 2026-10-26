# Idempotency and webhook delivery

Write requests that create payment reviews or refund requests require an Idempotency-Key header. Store the key with the operation result for 72 hours. Reusing the same key with a different request body returns HTTP 409. Replaying the same request returns the original operation result.

Webhook events can be delivered more than once or arrive out of order. Consumers must verify the webhook signature, deduplicate by event ID, and reconcile the event against current durable state. An acknowledgment means the event was accepted for processing, not that a payment operation finished.

Do not treat a model-generated statement as proof that a downstream API action succeeded. The durable operation record and provider acknowledgment determine the actual result.
