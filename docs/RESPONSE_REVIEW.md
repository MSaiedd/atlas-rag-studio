# Actual local answer review

The review below compares the recorded five-question HTTP walkthrough against the original fictional
Northstar source documents. It is an engineering spot-check, not independent expert validation.
All five requests completed streaming and passed structural reference checks. That did not make all five correct.
Full responses, retrieved passages, first-delta times and elapsed times are in `reports/live-api-smoke.json`.

| Question | Source expectation | Observed result |
| --- | --- | --- |
| Annual refund window and exceptions | Unused annual plans: 14 calendar days; manual approval; written contract override only | Correct window and contract exception, but omitted the unused-plan restriction and manual approval requirement |
| HTTP 429 retry | Honor Retry-After; otherwise full-jitter exponential 1/2/4/8 seconds capped at 30, five attempts; safe writes require idempotency | Correct retry timing and attempt limit; omitted the safe-write condition; used “restarting” for “retrying” once |
| Account compromise | Revoke sessions, notify security, verify ownership, rotate credentials, evaluate MFA, preserve evidence, P1 acknowledgment within 15 minutes | Partial procedure; “revolve” instead of “revoke”; omitted MFA and P1 acknowledgment timing |
| Arabic annual refund policy | Same annual-policy facts in clear Arabic | Preserved 14-day/unused-plan concepts, but phrasing is poor and some approval wording is unsupported |
| Exact enterprise exception days | No exact duration is documented; abstain or explain that the executed contract must be consulted | Nonresponsive monthly-plan answer; a cited but inadequate answer passed structural checks |

The CPU development model is useful for demonstrating the complete pipeline and measurable adaptation.
It is not acceptable as an autonomous high-stakes policy or security decision maker. Increasing model
capacity, improving reviewed training data and calibrating answer rejection require a new evaluation run.
The application keeps source inspection, feedback and full run reports available so these failures remain visible.
