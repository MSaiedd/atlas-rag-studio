"""Validate disposable portfolio containers, persistence, and non-root execution."""

import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def run(project):
    suffix = uuid.uuid4().hex[:10]
    name = "portfolio-check-" + suffix
    volume = "portfolio-check-data-" + suffix
    image = project + ":portfolio"
    token, operator = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    identities = json.dumps(
        {
            token: {"tenant": "demo", "user": "alice"},
            operator: {"tenant": "demo", "user": "staff", "role": "operator"},
        }
    )
    headers = {"Authorization": "Bearer " + token}
    mount = "/app/artifacts" if project == "arabic-support-lora" else "/app/data"
    command("volume", "create", volume)

    def launch():
        command(
            "run",
            "--rm",
            "--name",
            name,
            "-d",
            "-p",
            "127.0.0.1::8000",
            "-e",
            "API_TOKENS=" + identities,
            "-v",
            volume + ":" + mount,
            image,
        )
        address = "http://" + command("port", name, "8000/tcp").splitlines()[0]
        for _ in range(120):
            try:
                if httpx.get(address + "/health", timeout=1).status_code == 200:
                    return address
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        raise RuntimeError("Container failed to start: " + command("logs", name)[-2000:])

    try:
        if project == "supportpilot":
            command(
                "run",
                "--rm",
                "-v",
                volume + ":" + mount,
                image,
                "python",
                "-m",
                "supportpilot.seed",
            )
        elif project == "arabic-support-lora":
            command(
                "run",
                "--rm",
                "-v",
                volume + ":" + mount,
                image,
                "python",
                "-m",
                "support_lora.baseline",
            )
        address = launch()
        assert command("exec", name, "id", "-u") != "0"
        if project == "citewise":
            assert (
                httpx.post(
                    address + "/documents",
                    headers=headers,
                    json={"title": "Container policy", "text": "Refunds take five business days."},
                ).status_code
                == 201
            )
            answer = httpx.post(
                address + "/query", headers=headers, json={"question": "refunds"}
            ).json()
            assert "five" in answer["answer"] and answer["citations"]
            command("stop", name)
            address = launch()
            assert len(httpx.get(address + "/documents", headers=headers).json()) == 1
        elif project == "supportpilot":
            ticket = httpx.post(
                address + "/tickets",
                headers=headers,
                json={"message": "Please refund this order", "order_id": "DEMO-1001"},
            ).json()
            refund_id = ticket["refunds"][0]["id"]
            assert (
                httpx.post(
                    address + "/refunds/" + refund_id + "/decision",
                    headers=headers,
                    json={"approve": True},
                ).status_code
                == 403
            )
            result = httpx.post(
                address + "/refunds/" + refund_id + "/decision",
                headers={"Authorization": "Bearer " + operator},
                json={"approve": True},
            )
            assert result.json()["status"] == "approved"
            command("stop", name)
            address = launch()
            assert (
                httpx.get(address + "/tickets/" + ticket["id"], headers=headers).json()["refunds"][
                    0
                ]["status"]
                == "approved"
            )
        else:
            result = httpx.post(
                address + "/predict", headers=headers, json={"text": "أريد استرداد المبلغ"}
            )
            assert result.status_code == 200 and result.json()["backend"] == "tfidf-baseline"
            assert (
                httpx.post(address + "/predict", json={"text": "refund please"}).status_code == 401
            )
        report = {
            "project": project,
            "result": "passed",
            "image_id": command("image", "inspect", image, "--format", "{{.Id}}"),
            "non_root": True,
            "checks": "isolated container startup and API flow; named-volume persistence; refund approval for SupportPilot; baseline training/inference for LoRA project",
        }
        path = ROOT / "reports/container.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True)


if __name__ == "__main__":
    run("supportpilot")
