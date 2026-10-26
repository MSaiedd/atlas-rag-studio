"""Validate the built image, non-root execution and persistence without downloading models."""

import argparse
import json
import socket
import subprocess
import time
import uuid
from pathlib import Path

import httpx


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def wait(client):
    for _ in range(100):
        try:
            response = client.get("/health")
            if response.status_code == 200:
                return response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Container did not become live")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="atlas-rag-studio:local")
    args = parser.parse_args()
    name = "atlas-image-check-" + uuid.uuid4().hex[:10]
    volume = name + "-data"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    docker("volume", "create", volume)
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"127.0.0.1:{port}:8000",
            "-e",
            "ATLAS_MODEL_LOADING=false",
            "-e",
            "ATLAS_WORKER_ENABLED=false",
            "-e",
            "ATLAS_LOCAL_CLIENT_NETWORKS=127.0.0.0/8,172.16.0.0/12",
            "-v",
            volume + ":/app/data",
            args.image,
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            health = wait(client)
            assert client.get("/ready").status_code == 503
            assert "Atlas" in client.get("/").text
            uid = docker("exec", name, "id", "-u")
            assert uid != "0"
            collection = client.post("/api/collections", json={"name": "Image check"})
            collection.raise_for_status()
            collection_id = collection.json()["id"]
            uploaded = client.post(
                "/api/documents",
                data={"collection_id": collection_id},
                files={
                    "file": (
                        "policy.md",
                        b"# Original policy\nImage persistence check.",
                        "text/markdown",
                    )
                },
            )
            uploaded.raise_for_status()
            document_id = uploaded.json()["id"]
            docker("restart", name)
            wait(client)
            documents = client.get("/api/documents").json()
            assert any(row["id"] == document_id for row in documents)
            report = {
                "image_id": docker("image", "inspect", args.image, "--format", "{{.Id}}"),
                "uid": int(uid),
                "liveness": health,
                "checks": [
                    "frontend served",
                    "non-root user",
                    "unready without models",
                    "upload persisted across container restart",
                ],
                "models": "Disabled for image/persistence smoke. Actual neural execution is recorded separately.",
                "passed": True,
            }
            Path("reports").mkdir(exist_ok=True)
            Path("reports/container.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2))
    except Exception:
        print(docker("logs", name))
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, check=False)
        subprocess.run(["docker", "volume", "rm", volume], stdout=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    main()
