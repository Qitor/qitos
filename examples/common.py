"""Shared helpers for self-contained examples."""

from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from qitos.models import OpenAICompatibleModel
from qitos.trace import TraceWriter

DEFAULT_MODEL_BASE_URL = "https://api.siliconflow.cn/v1/"
DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 2048
DEFAULT_THEME = "research"


def add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--workspace", default="./playground", help="Optional workspace path")
    ap.add_argument("--model-base-url", default=DEFAULT_MODEL_BASE_URL)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--theme", default=DEFAULT_THEME)
    ap.add_argument("--trace-logdir", default="./runs")
    ap.add_argument("--trace-prefix", default="qitos")
    ap.add_argument("--disable-trace", action="store_true")
    ap.add_argument("--disable-render", action="store_true")


def build_model_from_args(args: argparse.Namespace) -> OpenAICompatibleModel:
    api_key = str(args.api_key).strip() or os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("QITOS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing API key. Set --api-key or OPENAI_API_KEY/QITOS_API_KEY.")
    return OpenAICompatibleModel(
        model=str(args.model_name),
        api_key=api_key,
        base_url=str(args.model_base_url) or None,
        temperature=float(args.temperature),
        max_tokens=int(args.max_tokens),
    )


def setup_workspace(path: str) -> Tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]:
    if path:
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True)
        return root, None
    temp_ctx: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
    return Path(temp_ctx.name), temp_ctx


def make_trace_writer(args: argparse.Namespace, case_name: str) -> TraceWriter | None:
    if bool(args.disable_trace):
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run_id = f"{args.trace_prefix}_{case_name}_{stamp}"
    return TraceWriter(
        output_dir=str(Path(args.trace_logdir).expanduser().resolve()),
        run_id=run_id,
        strict_validate=True,
        metadata={"model_id": str(args.model_name)},
    )
