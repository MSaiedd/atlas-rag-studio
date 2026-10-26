"""Record actual HTTP/SSE answers from a seeded local workspace; never substitutes models."""

import argparse
import json
import time
import uuid
from pathlib import Path

import httpx

QUESTIONS = [
    "What is the refund window for annual plans, and are there exceptions?",
    "How should I handle a 429 API response?",
    "What should we do when an employee reports a compromised account?",
    "ما سياسة استرداد الاشتراكات السنوية؟",
    "What is the exact enterprise refund exception window in days?",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--mode", choices=["base", "adapted"], default="adapted")
    parser.add_argument("--output", default="reports/live-api-smoke.json")
    parser.add_argument("--question", action="append", help="Override the example questions")
    args = parser.parse_args()
    report = {
        "purpose": "Actual-model local HTTP/SSE walkthrough; factual correctness requires source review",
        "mode": args.mode,
        "cases": [],
    }
    with httpx.Client(base_url=args.url, timeout=300) as client:
        client.get("/ready").raise_for_status()
        report["workspace"] = client.get("/api/workspace").json()
        for question in args.question or QUESTIONS:
            response = client.post("/api/conversations", json={"title": question[:100]})
            response.raise_for_status()
            conversation_id = response.json()["id"]
            started, first_token = time.perf_counter(), None
            frame, final, failure, delta_count = [], None, None, 0
            with client.stream(
                "POST",
                f"/api/conversations/{conversation_id}/messages",
                json={"question": question, "mode": args.mode, "request_id": uuid.uuid4().hex},
            ) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if line:
                        frame.append(line)
                        continue
                    name = next(
                        (part[6:].strip() for part in frame if part.startswith("event:")), ""
                    )
                    payload = "\n".join(
                        part[5:].lstrip() for part in frame if part.startswith("data:")
                    )
                    frame = []
                    if not payload:
                        continue
                    data = json.loads(payload)
                    if name == "delta":
                        delta_count += 1
                        if first_token is None:
                            first_token = (time.perf_counter() - started) * 1000
                    elif name == "complete":
                        final = data
                    elif name == "error":
                        failure = data
            case = {
                "question": question,
                "conversation_id": conversation_id,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "first_delta_ms": round(first_token) if first_token is not None else None,
                "delta_events": delta_count,
                "state": final.get("state") if final else "failed",
                "answer": final.get("content") if final else None,
                "citations": final.get("citations", []) if final else [],
                "error": failure,
            }
            report["cases"].append(case)
            print(
                json.dumps(
                    {
                        "question": question,
                        "state": case["state"],
                        "elapsed_ms": case["elapsed_ms"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Recorded {len(report['cases'])} real requests in {target}")


if __name__ == "__main__":
    main()
