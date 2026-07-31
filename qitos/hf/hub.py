"""Push/pull QitOS trace artifacts to/from HuggingFace Hub dataset repos."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _require_hf() -> Any:
    """Lazy-import huggingface_hub with a helpful error message."""
    try:
        import huggingface_hub  # noqa: F401
        return huggingface_hub
    except ImportError as exc:
        raise RuntimeError(
            "Missing optional dependency: huggingface_hub. "
            "Install with: pip install 'qitos[hf]'"
        ) from exc


_SENSITIVE_KEY_PATTERN = re.compile(r"api.?key|secret|token|password", re.IGNORECASE)


def sanitize_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive fields from a manifest dict before uploading.

    Returns a deep copy — the original is never mutated.
    """
    sanitized = copy.deepcopy(manifest)

    # Sanitize run_spec.environment
    run_spec = sanitized.get("run_spec")
    if isinstance(run_spec, dict):
        env = run_spec.get("environment")
        if isinstance(env, dict):
            keys_to_remove = [k for k in env if _SENSITIVE_KEY_PATTERN.search(k)]
            for k in keys_to_remove:
                del env[k]
            if "base_url" in env:
                env["base_url"] = "REDACTED"

    return sanitized


def push_run(
    run_dir: str | Path,
    repo_id: str,
    *,
    token: Optional[str] = None,
    revision: Optional[str] = None,
    private: bool = True,
) -> str:
    """Push a run directory to a HuggingFace Hub dataset repo.

    Returns the HF Hub URL for the run.
    """
    hf = _require_hf()

    run_path = Path(run_dir).expanduser().resolve()
    if not run_path.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_path}")

    # Create repo if needed
    hf.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True, token=token, private=private)

    run_id = run_path.name
    upload_kwargs: Dict[str, Any] = {"repo_id": repo_id, "repo_type": "dataset", "token": token}
    if revision:
        upload_kwargs["revision"] = revision

    # Canonical traces are the default.  Historical event/step traces remain
    # uploadable when a run predates the compact writer.
    for filename in ("manifest.json", "trajectory.jsonl", "events.jsonl", "steps.jsonl"):
        filepath = run_path / filename
        if not filepath.exists():
            continue

        if filename == "manifest.json":
            # Sanitize manifest before upload
            raw = json.loads(filepath.read_text(encoding="utf-8"))
            sanitized = sanitize_manifest(raw)
            # Write sanitized version to a temp location, then upload
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tmp:
                tmp.write(json.dumps(sanitized, ensure_ascii=False, indent=2))
                tmp_path = tmp.name
            try:
                hf.upload_file(
                    path_or_fileobj=tmp_path,
                    path_in_repo=f"{run_id}/{filename}",
                    **upload_kwargs,
                )
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        else:
            hf.upload_file(
                path_or_fileobj=str(filepath),
                path_in_repo=f"{run_id}/{filename}",
                **upload_kwargs,
            )

    # Upload any additional files (visual assets etc.)
    for extra in sorted(run_path.iterdir()):
        if extra.name in ("manifest.json", "trajectory.jsonl", "events.jsonl", "steps.jsonl"):
            continue
        if extra.is_file():
            hf.upload_file(
                path_or_fileobj=str(extra),
                path_in_repo=f"{run_id}/{extra.name}",
                **upload_kwargs,
            )

    return f"https://huggingface.co/datasets/{repo_id}/tree/main/{run_id}"


def pull_run(
    run_id: str,
    repo_id: str,
    output_dir: str | Path,
    *,
    token: Optional[str] = None,
    revision: Optional[str] = None,
) -> Path:
    """Download a run from HuggingFace Hub to a local directory.

    Returns the local run directory path.
    """
    hf = _require_hf()

    out_path = Path(output_dir).expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    download_kwargs: Dict[str, Any] = {
        "repo_id": repo_id,
        "repo_type": "dataset",
        "token": token,
        "allow_patterns": [f"{run_id}/*"],
    }
    if revision:
        download_kwargs["revision"] = revision

    cached = hf.snapshot_download(**download_kwargs)

    # Move downloaded files to the target directory
    cached_dir = Path(cached) / run_id
    target_dir = out_path / run_id
    if cached_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in cached_dir.iterdir():
            dest = target_dir / f.name
            if not dest.exists():
                dest.write_bytes(f.read_bytes())

    return target_dir


def list_remote_runs(
    repo_id: str,
    *,
    token: Optional[str] = None,
) -> List[str]:
    """List run IDs available in a HuggingFace Hub dataset repo."""
    hf = _require_hf()

    try:
        tree = hf.list_repo_tree(repo_id=repo_id, repo_type="dataset", token=token)
        run_ids: List[str] = []
        for item in tree:
            # Items at the top level are run directories
            if hasattr(item, "path") and "/" not in item.path:
                run_ids.append(item.path)
            elif hasattr(item, "rfilename"):
                name = item.rfilename
                if "/" not in name and not name.startswith("."):
                    run_ids.append(name)
        return sorted(set(run_ids))
    except Exception:
        return []


__all__ = ["sanitize_manifest", "push_run", "pull_run", "list_remote_runs"]
