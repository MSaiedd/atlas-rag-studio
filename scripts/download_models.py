"""Download pinned public weights; skip alternate ONNX/OpenVINO and duplicate weight formats."""

import os

from atlas_rag.config import Settings


def main():
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    from huggingface_hub import snapshot_download

    settings = Settings()
    for model, revision in (
        (settings.embedding_model, settings.embedding_revision),
        (settings.reranker_model, settings.reranker_revision),
        (settings.model_id, settings.model_revision),
    ):
        print(f"Downloading {model} at {revision}", flush=True)
        snapshot_download(
            model,
            revision=revision,
            allow_patterns=["*.safetensors", "*.json", "*.txt", "*.model", "*.jinja"],
            ignore_patterns=["onnx/*", "openvino/*"],
            max_workers=2,
        )
    print("All configured weights are cached. Set ATLAS_OFFLINE=true for offline operation.")


if __name__ == "__main__":
    main()
