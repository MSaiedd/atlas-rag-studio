import json
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request

from atlas_rag.auth import Authentication
from atlas_rag.config import Settings
from atlas_rag.documents import extract_pages
from atlas_rag.evaluate import score_answer
from atlas_rag.generation import ABSTENTION
from atlas_rag.training import encode_row, read_dataset


def test_pdf_process_retains_pages_and_enforces_character_budget():
    raw = (Path(__file__).parent / "fixtures/sample-policy.pdf").read_bytes()
    pages = extract_pages(raw, "sample.pdf", 10000)
    assert pages[0][0] == 1 and "14 days" in pages[0][1]
    assert pages[1][0] == 2 and "five business days" in pages[1][1]
    with pytest.raises(ValueError, match="ingestion limit"):
        extract_pages(raw, "sample.pdf", 10)


def test_oidc_verification_rejects_expired_wrong_audience_and_bad_roles():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer="https://identity.example",
        oidc_audience="atlas",
        oidc_jwks_url="https://identity.example/keys",
    )
    auth = Authentication(settings)
    auth.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    claims = {
        "sub": "alice",
        "workspace_id": "alpha",
        "iss": settings.oidc_issuer,
        "aud": "atlas",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "roles": ["editor"],
    }

    def call(values):
        token = jwt.encode(values, private, algorithm="RS256")
        return auth(
            Request({"type": "http", "headers": [(b"authorization", ("Bearer " + token).encode())]})
        )

    identity = call(claims)
    assert identity.tenant == "alpha" and identity.role == "editor"
    for changes in ({"exp": 1}, {"aud": "other"}, {"roles": "notadmin"}, {"workspace_id": ""}):
        with pytest.raises(HTTPException) as error:
            call({**claims, **changes})
        assert error.value.status_code == 401


def test_local_mode_rejects_remote_clients():
    auth = Authentication(Settings())
    request = Request({"type": "http", "headers": [], "client": ("198.51.100.10", 5000)})
    with pytest.raises(HTTPException) as error:
        auth(request)
    assert error.value.status_code == 403


def test_scenario_split_and_response_masking(tmp_path):
    root = Path(__file__).resolve().parents[1] / "data/training"
    data = read_dataset(root)
    assert {name: len(rows) for name, rows in data.items()} == {
        "train": 240,
        "validation": 60,
        "test": 80,
    }
    for split in ("train", "validation", "test"):
        (tmp_path / f"{split}.jsonl").write_text(json.dumps(data["train"][0]) + "\n")
    with pytest.raises(ValueError, match="leakage"):
        read_dataset(tmp_path)

    class Tokenizer:
        eos_token = "!"

        def apply_chat_template(self, *args, **kwargs):
            return [1, 2, 3]

        def __call__(self, *args, **kwargs):
            return {"input_ids": [4, 5]}

    encoded = encode_row(Tokenizer(), data["train"][0], 10)
    assert encoded["labels"] == [-100, -100, -100, 4, 5]
    with pytest.raises(ValueError, match="never truncate"):
        encode_row(Tokenizer(), data["train"][0], 4)


def test_abstention_scoring_does_not_reward_malformed_answers():
    row = {"expected_terms": [], "answerable": False}
    assert score_answer(row, ABSTENTION, [])["abstention_correct"]
    assert not score_answer(row, "An invented answer [999]", [])["citation_valid"]


def test_real_adapter_update_and_reload(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model
    from transformers import Qwen2Config, Qwen2ForCausalLM

    torch.set_num_threads(2)
    torch.manual_seed(42)
    config = Qwen2Config(
        vocab_size=32,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=1,
        num_attention_heads=2,
        num_key_value_heads=2,
    )
    base = Qwen2ForCausalLM(config)
    path = tmp_path / "base"
    base.save_pretrained(path)
    model = get_peft_model(
        base,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM, r=2, lora_alpha=4, target_modules=["q_proj", "v_proj"]
        ),
    )
    trainable = {
        name: value.detach().clone()
        for name, value in model.named_parameters()
        if value.requires_grad
    }
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=0.01)
    ids = torch.tensor([[1, 4, 5, 6, 2]])
    labels = ids.clone()
    labels[:, :2] = -100
    loss = model(input_ids=ids, labels=labels).loss
    loss.backward()
    optimizer.step()
    assert any(
        not torch.equal(trainable[n], p) for n, p in model.named_parameters() if n in trainable
    )
    output = tmp_path / "adapter"
    model.save_pretrained(output)
    model.eval()
    reloaded = PeftModel.from_pretrained(Qwen2ForCausalLM.from_pretrained(path), output).eval()
    with torch.no_grad():
        torch.testing.assert_close(model(input_ids=ids).logits, reloaded(input_ids=ids).logits)
