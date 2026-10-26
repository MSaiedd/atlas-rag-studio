"""Train the answer generator to ground responses in evidence; no document memorization objective."""

import argparse
import hashlib
import importlib.metadata
import json
import random
import time
from pathlib import Path
from types import SimpleNamespace

from .config import Settings
from .database import Database, Experiment
from .generation import build_messages


def read_dataset(directory):
    splits, groups, ids = {}, set(), set()
    for split in ("train", "validation", "test"):
        rows = [
            json.loads(line)
            for line in (Path(directory) / f"{split}.jsonl").read_text().splitlines()
            if line.strip()
        ]
        if not rows:
            raise ValueError("Each dataset split must be non-empty")
        current = {row["scenario_group"] for row in rows}
        if current & groups:
            raise ValueError("Scenario-group leakage across training/validation/test splits")
        groups.update(current)
        for row in rows:
            if row["id"] in ids or not row["answer"].strip() or not row["contexts"]:
                raise ValueError("Duplicate IDs or empty supervised examples")
            ids.add(row["id"])
        splits[split] = rows
    return splits


def encode_row(tokenizer, row, max_length):
    passages = [SimpleNamespace(**context) for context in row["contexts"]]
    prefix = tokenizer.apply_chat_template(
        build_messages(row["question"], passages), tokenize=True, add_generation_prompt=True
    )
    target = tokenizer(row["answer"] + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
    if len(prefix) + len(target) > max_length:
        raise ValueError(f"{row['id']} exceeds max_length; never truncate a supervised answer")
    return {
        "input_ids": prefix + target,
        "attention_mask": [1] * (len(prefix) + len(target)),
        "labels": [-100] * len(prefix) + target,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/training")
    parser.add_argument("--output", default="artifacts/grounded-lora")
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--revision", default="7ae557604adf67be50417f59c2c2f167def9a775")
    parser.add_argument("--steps", type=int, default=64)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=768)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--qlora", action="store_true")
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    if min(args.steps, args.grad_accum, args.max_length) < 1:
        parser.error("Training limits must be positive")
    import torch
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed

    settings = Settings()
    torch.set_num_threads(settings.cpu_threads)
    set_seed(args.seed)
    splits = read_dataset(args.data)
    if args.qlora and not torch.cuda.is_available():
        parser.error("QLoRA requires a working CUDA GPU")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model, revision=args.revision, local_files_only=settings.offline
    )
    tokenizer.pad_token = tokenizer.eos_token
    kwargs = {
        "revision": args.revision,
        "local_files_only": settings.offline,
        "dtype": torch.float32,
    }
    if args.qlora:
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        kwargs.update(
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=dtype,
            ),
            device_map={"": 0},
            dtype=dtype,
        )
    base = AutoModelForCausalLM.from_pretrained(args.model, **kwargs)
    revision = getattr(base.config, "_commit_hash", None) or args.revision
    if args.qlora:
        base = prepare_model_for_kbit_training(base)
    model = get_peft_model(
        base,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"],
        ),
    )
    if not args.qlora:
        model.to("cuda" if torch.cuda.is_available() else "cpu")
    model.config.use_cache = False
    encoded = {
        split: [encode_row(tokenizer, row, args.max_length) for row in rows]
        for split, rows in splits.items()
        if split != "test"
    }
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.learning_rate
    )
    order = list(range(len(encoded["train"])))
    rng = random.Random(args.seed)
    rng.shuffle(order)
    position, losses = 0, []

    def batch(row):
        return {key: torch.tensor([value], device=model.device) for key, value in row.items()}

    def validation_loss():
        total, count = 0.0, 0
        for row in encoded["validation"]:
            n = sum(token != -100 for token in row["labels"][1:])
            total += model(**batch(row)).loss.item() * n
            count += n
        return total / count

    started = time.perf_counter()
    model.eval()
    with torch.no_grad(), model.disable_adapter():
        base_loss = validation_loss()
    model.train()
    for step in range(args.steps):
        optimizer.zero_grad(set_to_none=True)
        current = 0.0
        for _ in range(args.grad_accum):
            if position == len(order):
                rng.shuffle(order)
                position = 0
            row = encoded["train"][order[position]]
            position += 1
            loss = model(**batch(row)).loss
            if not torch.isfinite(loss):
                raise RuntimeError("Training loss became non-finite")
            (loss / args.grad_accum).backward()
            current += loss.item() / args.grad_accum
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        optimizer.step()
        losses.append(current)
        print(
            json.dumps({"step": step + 1, "total": args.steps, "response_token_loss": current}),
            flush=True,
        )
    model.eval()
    with torch.no_grad():
        tuned_loss = validation_loss()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    report = {
        "schema_version": 1,
        "method": "NF4 QLoRA" if args.qlora else "LoRA",
        "model": args.model,
        "revision": revision,
        "steps": args.steps,
        "examples_seen": args.steps * args.grad_accum,
        "seed": args.seed,
        "learning_rate": args.learning_rate,
        "gradient_accumulation": args.grad_accum,
        "max_length": args.max_length,
        "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "dataset_counts": {key: len(rows) for key, rows in splits.items()},
        "dataset_hashes": {
            name: hashlib.sha256((Path(args.data) / f"{name}.jsonl").read_bytes()).hexdigest()
            for name in splits
        },
        "losses": losses,
        "base_validation_loss": base_loss,
        "validation_loss": tuned_loss,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "device": str(model.device),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "peft", "accelerate")
        },
        "limitation": "Original synthetic, templated scenario fixture. Validation loss does not establish response safety or real-world quality.",
    }
    (output / "training_report.json").write_text(json.dumps(report, indent=2) + "\n")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/training.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.register:
        database = Database(settings.database_url)
        with database.session() as session:
            session.add(
                Experiment(
                    tenant=settings.local_tenant,
                    kind="training",
                    name=f"Grounded LoRA · {args.steps} steps",
                    report=report,
                )
            )
        database.engine.dispose()
    print(
        json.dumps(
            {
                "adapter": str(output),
                "base_validation_loss": base_loss,
                "validation_loss": tuned_loss,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
