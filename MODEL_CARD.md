# Model and data card

## Components

- Generator: `Qwen/Qwen2.5-0.5B-Instruct`, pinned revision in configuration. Used for CPU development.
- Embeddings: `intfloat/multilingual-e5-small`; frozen pretrained weights with query/passage prefixes.
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`; frozen pretrained question/passage classifier.
- Adaptation: rank-8 LoRA on the generator's query/value attention projections. Optional NF4 QLoRA.

Only the generator's adapter is custom trained. The retrieval models are not represented as custom
trained artifacts. Model weights retain their upstream licenses; code and original data are MIT.

## Objective

Generate concise English/Arabic answers using supplied source passages, preserve source references,
and abstain on unsupported questions. Do not memorize changing policy values or execute business actions.

## Data provenance and split

The fixture is original synthetic text: 240 training, 60 validation and 80 test examples.
Organization/scenario groups stay within a single split before bilingual expansion. Policy values
change across organizations. Supported, multi-source, unsupported and injected-instruction cases
are included. No real customer records are used.

Task templates recur across splits. This deliberately tests counterfactual grounding under those
templates; it does not establish novel-domain generalization. Exact group separation cannot remove
all semantic similarity. Reference answers are authored examples, not independently human-reviewed labels.

## Training and evaluation

Only response tokens receive supervision. Overlong targets are rejected rather than truncated.
Run reports include dataset hashes, model revision, seed, trainable parameter count and versions.
Held-out evaluation exercises actual retrieval and base/adapted generation. Reference fact coverage
is a lexical proxy. Structural citation validation is not proof of claim-level support.

Review answers with Arabic/English domain reviewers for factual support, citation support, language
quality, correct abstention and resistance to document instructions. Record disagreements and failures.

## Limitations

Small synthetic fixtures and a small development model are not a validated enterprise assistant.
The model can misread documents, copy a wrong number, over-abstain, hallucinate, or follow document
instructions. Document-grounded output still needs human review for important decisions.
The model has no payment or account-modification tools. GPU QLoRA and external inference-provider
behavior must be verified on their actual infrastructure.

Recorded results and measured boundaries are documented in `docs/VALIDATION.md` and `reports/`.
