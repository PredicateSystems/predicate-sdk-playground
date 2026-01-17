#!/usr/bin/env python3
"""
Download Qwen 2.5 7B weights to the local HF cache.

This is a warm-up script only (no model load), so it is safe to run on
machines without enough RAM/VRAM for inference.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> int:
    model_id = os.getenv("QWEN_7B_MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")
    local_dir = os.getenv("QWEN_7B_LOCAL_DIR")
    hf_token = os.getenv("HF_TOKEN")

    print(f"[info] Downloading model: {model_id}")
    if local_dir:
        print(f"[info] Using local_dir: {local_dir}")
        Path(local_dir).mkdir(parents=True, exist_ok=True)

    try:
        snapshot_path = snapshot_download(
            repo_id=model_id,
            local_dir=local_dir,
            token=hf_token,
            local_dir_use_symlinks=False,
        )
    except Exception as exc:
        print(f"[error] Download failed: {exc}", file=sys.stderr)
        return 1

    print(f"[info] Download complete.")
    print(f"[info] Cache path: {snapshot_path}")
    print("[info] You can now load the model with Transformers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
