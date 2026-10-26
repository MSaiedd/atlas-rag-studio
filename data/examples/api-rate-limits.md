# API rate limits and retries

## Workspace quota
The fictional Northstar API permits 600 requests per minute per workspace, with a short burst limit of 30 requests. A request above the limit receives HTTP 429. The response includes a Retry-After header in seconds.

## Retry behavior
When a request receives 429, honor Retry-After before sending another request. When the header is missing, use exponential backoff with full jitter: initial delays of approximately 1, 2, 4, and 8 seconds, capped at 30 seconds. Stop after five attempts and surface a recoverable error to the caller. Retrying immediately in a tight loop increases contention.

## Safe writes
Only retry a write when it carries an idempotency key or the endpoint documentation explicitly states the operation is idempotent. Authentication failures such as HTTP 401 require credential repair, not blind retries.
