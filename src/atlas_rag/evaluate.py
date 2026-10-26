"""End-to-end RAG evaluation with real retrieval, references and base/adapter comparisons."""

import argparse
import json
import random
import tempfile
import threading
import time
from pathlib import Path

from .auth import Identity
from .config import Settings
from .database import Collection, Database, Experiment
from .documents import index_document, upload_document
from .generation import LocalGenerator, abstention_for, validate_answer
from .retrieval import NeuralRetrieval, VectorIndex, retrieve
from .training import read_dataset


def score_answer(row, answer, passages):
    try:
        refs, abstained = validate_answer(answer, passages)
        valid = True
    except ValueError:
        refs, abstained, valid = [], False, False
    coverage = (
        sum(term.casefold() in answer.casefold() for term in row["expected_terms"])
        / len(row["expected_terms"])
        if row["expected_terms"]
        else float(abstained)
    )
    return {
        "citation_valid": valid,
        "fact_coverage": coverage,
        "abstention_correct": valid and abstained == (not row["answerable"]),
        "abstained": abstained,
        "citations": refs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["all", "retrieval"], default="all")
    parser.add_argument("--data", default="data/training")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="reports/evaluation.json")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("limit must be non-negative")
    settings = Settings()
    rows = read_dataset(args.data)["test"]
    if args.limit:
        rows = random.Random(42).sample(rows, min(len(rows), args.limit))
    encoder = NeuralRetrieval(settings)
    report = {
        "schema_version": 1,
        "dataset": "Original counterfactual synthetic fixture; scenario groups held out from training",
        "sample_count": len(rows),
        "selected_test_ids": [row["id"] for row in rows],
        "embedding_revision": encoder.revision,
        "reranker_revision": encoder.reranker_revision,
        "retrieval": {},
        "generation": {},
        "examples": [],
        "limitation": "Synthetic templates recur across scenario groups. Fact coverage is a lexical proxy, not semantic faithfulness. These runs do not establish production quality or serving capacity.",
    }
    with tempfile.TemporaryDirectory(prefix="atlas-evaluation-") as temporary:
        isolated = settings.model_copy(
            update={
                "data_dir": Path(temporary),
                "database_url": f"sqlite:///{temporary}/evaluation.db",
                "qdrant_url": None,
            }
        )
        db = Database(isolated.database_url)
        vectors = VectorIndex(isolated, encoder.dimension, encoder.fingerprint)
        identity = Identity("evaluation", "evaluator", "admin")
        collections = {}
        # Each organization's corpus includes all its test context documents, including hard negatives.
        all_rows = read_dataset(args.data)["test"]
        for group in sorted({row["scenario_group"] for row in rows}):
            with db.session() as session:
                collection = Collection(tenant=identity.tenant, name=group)
                session.add(collection)
                session.flush()
                collections[group] = collection.id
            documents = {
                context["title"]: context
                for row in all_rows
                if row["scenario_group"] == group
                for context in row["contexts"]
            }
            for title, context in documents.items():
                uploaded = upload_document(
                    db,
                    isolated,
                    identity,
                    collections[group],
                    title + ".txt",
                    context["text"].encode(),
                )
                index_document(db, isolated, vectors, encoder, uploaded["id"])
        results = {}
        for method in ("lexical", "dense", "hybrid", "reranked"):
            recalls, reciprocals = [], []
            for index, row in enumerate(rows):
                result = retrieve(
                    db,
                    isolated,
                    vectors,
                    encoder,
                    identity,
                    row["question"],
                    [collections[row["scenario_group"]]],
                    method,
                )
                if method == "reranked":
                    results[row["id"]] = result
                titles = [p.title for p in result.passages]
                if row["expected_titles"]:
                    expected = set(row["expected_titles"])
                    recalls.append(len(expected & set(titles)) / len(expected))
                    ranks = [i + 1 for i, title in enumerate(titles) if title in expected]
                    reciprocals.append(1 / min(ranks) if ranks else 0)
                print(
                    json.dumps(
                        {
                            "stage": "retrieval",
                            "method": method,
                            "case": index + 1,
                            "total": len(rows),
                        }
                    ),
                    flush=True,
                )
            report["retrieval"][method] = {
                "recall_at_5": sum(recalls) / len(recalls) if recalls else 0,
                "mrr": sum(reciprocals) / len(reciprocals) if reciprocals else 0,
                "samples": len(recalls),
            }
        if args.mode == "all":
            generator = LocalGenerator(settings)
            report["model"] = settings.model_id
            modes = ["base", "adapted"] if generator.has_adapter else ["base"]
            for mode in modes:
                values = []
                for index, row in enumerate(rows):
                    started = time.perf_counter()
                    passages = retrieve(
                        db,
                        isolated,
                        vectors,
                        encoder,
                        identity,
                        row["question"],
                        [collections[row["scenario_group"]]],
                        "reranked",
                    ).passages
                    if passages:
                        prepared = generator.prepare(row["question"], passages)
                        answer = "".join(generator.stream(prepared, mode, threading.Event()))
                        passages = prepared.passages
                    else:
                        answer = abstention_for(row["question"])
                    score = score_answer(row, answer, passages)
                    values.append({**score, "latency_ms": (time.perf_counter() - started) * 1000})
                    report["examples"].append(
                        {
                            "id": row["id"],
                            "language": row["language"],
                            "question": row["question"],
                            "expected": row["answer"],
                            "answer": answer,
                            "mode": mode,
                            "retrieved_titles": [p.title for p in passages],
                            "generation_used": bool(passages),
                            **score,
                        }
                    )
                    print(
                        json.dumps(
                            {
                                "stage": "generation",
                                "mode": mode,
                                "case": index + 1,
                                "total": len(rows),
                                "citation_valid": score["citation_valid"],
                                "fact_coverage": score["fact_coverage"],
                            }
                        ),
                        flush=True,
                    )
                report["generation"][mode] = {
                    "samples": len(values),
                    "citation_validity": sum(v["citation_valid"] for v in values) / len(values),
                    "fact_coverage": sum(v["fact_coverage"] for v in values) / len(values),
                    "abstention_accuracy": sum(v["abstention_correct"] for v in values)
                    / len(values),
                    "latency_ms": sum(v["latency_ms"] for v in values) / len(values),
                }
        vectors.close()
        db.engine.dispose()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.register:
        database = Database(settings.database_url)
        with database.session() as session:
            session.add(
                Experiment(
                    tenant=settings.local_tenant,
                    kind="evaluation",
                    name=f"Grounded RAG · {len(rows)} held-out cases",
                    report=report,
                )
            )
        database.engine.dispose()
    print(
        json.dumps(
            {
                "output": str(output),
                "retrieval": report["retrieval"],
                "generation": report["generation"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
