# Validation evidence

This document distinguishes actual model execution from deterministic regression fixtures.
No public deployment or production traffic capacity is claimed.

## Backend regression

`pytest -q --disable-warnings` — 18 passed locally, including real adapter update/save/reload
with a tiny randomly initialized architecture. Neural retrieval/generation are substituted in
workspace regression fixtures; SQL, Qdrant, HTTP routes and authorization remain real.
The Python 3.12 CI job installs CPU model libraries for the tiny adapter contract test;
the core-only Python 3.11 job skips that optional test.

The suite covers workspace/user isolation, signed JWT validation, expired/wrong-audience tokens,
role checks, cross-origin writes, duplicate ingestion, invalid citations, absent evidence, cancellation,
concurrent-conversation admission, idempotent messages, feedback, source deletion and reindexing.
PDF extraction is tested in the actual resource-bounded child process with a two-page PDF.

## PostgreSQL and authenticated Qdrant

`ATLAS_TEST_DATABASE_URL=postgresql+psycopg://.../atlas_test ATLAS_TEST_QDRANT_URL=http://127.0.0.1:16333 ATLAS_TEST_QDRANT_API_KEY=... pytest tests/test_workspace.py -q --disable-warnings` — 12 passed locally.
PostgreSQL 17.11 and Qdrant 1.20.0 ran in isolated local containers. The configured test database
is explicitly required to be named atlas_test before the fixture clears its own records.
This validates server persistence/query/filter paths, not a replicated production deployment.

## Frontend and browser

- `npm run check --prefix frontend` — passed TypeScript checking.
- `npm test --prefix frontend` — 4 passed; Arabic UTF-8 and CRLF framing across byte boundaries,
  interrupted streaming, provider unavailability and permission errors.
- `npm audit --prefix frontend --audit-level=moderate` — zero reported vulnerabilities after updating Vitest.
- `npm run build --prefix frontend` — passed.
- `python scripts/browser_smoke.py` — passed desktop upload/index/chat/citation/feedback/trace/preview
  and phone navigation/layout checks, with no uncaught browser errors. Neural components in this
  browser fixture are simulated. Uploaded markup is rendered as text and does not execute.

Actual-model walkthroughs, training and evaluation reports are recorded separately in reports/.
Live model screenshots in docs/screenshots/ are separate from CI fixture screenshots in reports/browser/.

## Initial model-quality finding

An initial refund-only grounding fixture produced weak answers on API retry and incident procedures
outside its training scope, and a complex refund answer failed structural citation validation.
Those observations led to a broader fixture covering technical and operational tasks. The earlier
narrow fixture and adapter remain private development artifacts; current source data and release
reports identify the final dataset hashes. Training loss alone is not an answer-quality metric.

## External validation boundaries

CUDA QLoRA, a real enterprise OIDC provider, public TLS/proxy operation, a live external generation
provider, replicated services, high-traffic latency/SLA, and live backup/restore procedures have not
been established by these local checks. The code and deployment configuration expose those paths;
they require validation in the target environment.

## Built image

`docker build -t atlas-rag-studio:local .` — passed.
`python scripts/container_smoke.py` — passed: image serves the built frontend, runs as UID 1000,
returns unready while models are disabled, and preserves an uploaded document across restart.
This image/persistence smoke intentionally disables neural loading. Actual model checks run separately.
See `reports/container.json` for the image identifier and check list.

## Full retrieval fixture

`ATLAS_OFFLINE=1 python -m atlas_rag.evaluate --mode retrieval --output reports/retrieval.json --register` — completed all 80 held-out cases.
Recall/MRR use the 64 answerable cases; unsupported cases do not have expected source titles.

| Method | Recall@5 | MRR |
| --- | ---: | ---: |
| Lexical | 0.96875 | 0.70000 |
| Dense | 1.00000 | 1.00000 |
| Hybrid | 1.00000 | 0.84375 |
| Reranked hybrid | 1.00000 | 0.95833 |

Dense retrieval ranked this small fixture best; reranking is not claimed to improve every workload.
These measurements do not establish real-world recall. Full raw output is in `reports/retrieval.json`.

## Recorded generator training

`ATLAS_OFFLINE=1 python -m atlas_rag.training --steps 128 --grad-accum 1 --max-length 640 --output artifacts/grounded-lora-v2 --register` — completed on CPU in 1,538.29 seconds.
The final artifact was installed at artifacts/grounded-lora after completion.
540,672 parameters were trainable. The run saw 128 examples from 240 training rows (a partial epoch).
Token-weighted validation NLL on 60 rows fell from 1.897993 to 0.689405.
This is a development training run; the NLL decrease does not establish answer correctness.
The full settings, losses, dataset hashes and library versions are in `reports/training.json`.

## Hosted CI and release distribution

[GitHub Actions run 40266320122](https://github.com/MSaiedd/atlas-rag-studio/actions/runs/40266320122) — all five jobs passed:
Python 3.11, Python 3.12 (including the real tiny adapter contract), frontend, PostgreSQL/Qdrant,
and Chromium browser flow. These checks ran against source commit e0d7e9d912e4be1e041cc19406e983292400c5f7.

`python scripts/download_adapter.py` — tested from an empty temporary working directory against
the public v0.2.0 release. Archive SHA-256 matched the embedded expected value, extraction succeeded,
and the installed safetensors bytes matched the locally trained adapter exactly.
The fixture adapter is a development artifact; downloading it does not change its quality limits.

## Actual base/adapted generation comparison

`ATLAS_OFFLINE=1 python -m atlas_rag.evaluate --mode all --limit 20 --register` — completed.
The fixed-seed sample has 20 of 80 held-out rows: 9 English and 11 Arabic, 17 answerable and 3 unsupported.
All retrieval and generation components were real pretrained models; no neural fixture substitutes were used.
Each generation request included fresh retrieval, and both modes used the same pinned base model.

| Metric | Base | LoRA adapted |
| --- | ---: | ---: |
| Structural citation validity | 10% | 80% |
| Lexical reference fact coverage | 57.5% | 77.5% |
| Valid answer/abstention decision | 10% | 80% |
| Mean retrieval + generation time, CPU | 14.07 s | 12.75 s |

Timing is a sequential local workload, including abstentions, not a concurrent serving benchmark.
Fact coverage is a lexical proxy that includes unsupported-case abstention; it is not semantic accuracy.
The abstention-decision metric also requires structural validity, so it must not be read as an independent safety score.
Four adapted answers failed structural validation, with Arabic injection/operational cases among the failures.
Some valid answers omit requested facts; Arabic can contain garbled phrasing. No production-quality claim follows
from this small templated fixture. Raw questions, references and answers are in `reports/evaluation.json`.

## Actual running application

The local checkout is now `atlas-rag-studio`. `python ../local_apps.py start --app atlas-rag-studio`
started the user service on loopback port 8001 with the real E5, reranker, Qwen base and saved adapter.
`python scripts/live_smoke.py` — five real HTTP/SSE requests completed, taking 10.4–21.0 seconds
on this CPU. Eleven source documents were already indexed. Answers and source passages were reviewed
in [RESPONSE_REVIEW.md](RESPONSE_REVIEW.md): incomplete procedures, Arabic quality issues and a
nonresponsive unsupported-field answer remain, despite valid reference formatting.

`python scripts/capture_workspace.py` — passed against the real running service; captured chat,
knowledge, evaluation, training and fresh-phone screenshots, with no uncaught browser errors.
These images show actual source state, trained-model output and measured run records.

`python scripts/live_smoke.py --question "What is the phone number of Northstar's finance director?" --output reports/abstention-smoke.json` — completed in 1.469 seconds with the canonical insufficient-evidence answer.
This separate success does not erase the harder unsupported-field failure recorded above.
