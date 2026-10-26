# Release readiness checklist

Every release requires passing automated checks, a tested database migration, an operator-visible rollback plan, and a recorded build identifier. Deploy to staging before production and run representative browser and API checks.

Use a small canary before broad rollout. Observe p95 request latency, error rate, queue age, and database saturation. Pause rollout when errors exceed the agreed service target or when persistent data integrity checks fail.

Schema changes should remain compatible with the previous application version until rollback is no longer required. A successful local test is not evidence of a successful public deployment.
