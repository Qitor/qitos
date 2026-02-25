"""Content-first extraction helpers for terminal render hooks."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from rich import box
from rich.syntax import Syntax
from rich.table import Table

from .events import RenderEvent

_THOUGHT_RE = re.compile(r"Thought\s*:\s*(.*?)(?:\n[A-Za-z_ ]+\s*:|\Z)", re.IGNORECASE | re.DOTALL)
_NOISE_KEYS = {"latency_ms", "run_id", "error_category", "ts", "step_id", "phase", "hook"}


class ContentFirstRenderer:
    """Extract concise thought/action/observation/memory blocks from events."""

    def __init__(self, max_preview_chars: int = 500):
        self.max_preview_chars = max(120, int(max_preview_chars))

    def task_text(self, task: str, max_steps: Optional[int] = None) -> str:
        if max_steps is None:
            return task
        return f"{task} [max_steps={max_steps}]"

    def thought_text(self, event: RenderEvent) -> Optional[str]:
        payload = event.payload or {}
        if event.node == "decision":
            rationale = payload.get("rationale")
            if isinstance(rationale, str) and rationale.strip():
                return self._truncate(rationale.strip(), self.max_preview_chars)
            return None
        if event.node == "model_output":
            raw = payload.get("raw_output")
            if not isinstance(raw, str):
                return None
            m = _THOUGHT_RE.search(raw)
            if m:
                return self._truncate(m.group(1).strip(), self.max_preview_chars)
            return self._truncate(raw.strip(), self.max_preview_chars)
        return None

    def action_summary(self, event: RenderEvent) -> Optional[Dict[str, str]]:
        payload = event.payload or {}
        if event.node == "planned_actions":
            actions = payload.get("actions")
            if isinstance(actions, list) and actions:
                return self._action_from_dict(actions[0])
            return None

        if event.node == "tool_invocations":
            items = payload.get("tool_invocations")
            if isinstance(items, list) and items:
                first = items[0] if isinstance(items[0], dict) else {}
                name = str(first.get("tool_name") or first.get("name") or "tool")
                status = str(first.get("status") or "").lower()
                return {
                    "label": name.upper().replace("_", " "),
                    "detail": "",
                    "status": "error" if status == "error" else "success",
                }
            return None
        return None

    def observation_summary(self, event: RenderEvent) -> Optional[Dict[str, Any]]:
        payload = event.payload or {}
        data = payload.get("observation") if event.node == "observation" else payload.get("action_results")
        if data is None:
            return None
        if isinstance(data, list) and data:
            item = data[0]
        else:
            item = data
        if not isinstance(item, dict):
            return {"status": "neutral", "title": "Observation", "body": self._truncate(self._to_text(item), 220)}

        cleaned = self._strip_noise(item)
        rows = self._extract_search_rows(cleaned)
        if rows:
            table = Table(show_header=True, header_style="bold", box=box.SIMPLE, show_edge=False)
            table.add_column("Title")
            table.add_column("URL")
            for title, short_url in rows[:6]:
                table.add_row(self._truncate(title, 80), short_url)
            return {"status": "success", "title": "Search Results", "table": table}

        syntax = self._extract_syntax(cleaned)
        if syntax is not None:
            return {"status": "success", "title": "Structured Output", "syntax": syntax}

        title = str(cleaned.get("title") or cleaned.get("name") or cleaned.get("status") or "Observation")
        url = str(cleaned.get("url") or cleaned.get("source_url") or cleaned.get("target_url") or "")
        err = cleaned.get("error")
        if err:
            return {
                "status": "error",
                "title": self._truncate(str(err), 120),
                "url": self._short_url(url) if url else "",
                "body": self._truncate(self._to_text(cleaned.get("content", "")), 180),
            }

        body = self._best_body(cleaned)
        return {
            "status": "success",
            "title": self._truncate(title, 120),
            "url": self._short_url(url) if url else "",
            "body": self._truncate(body, 220) if body else "",
        }

    def state_summary(self, event: RenderEvent) -> Optional[Dict[str, Any]]:
        """Extract compact state stats from state snapshot payload."""
        if event.node not in {"state", "observation"}:
            return None
        payload = event.payload or {}
        obs = payload.get("observation")
        if not isinstance(obs, dict):
            return None

        scratchpad = obs.get("scratchpad")
        scratchpad_items = 0
        scratchpad_tokens = 0
        if isinstance(scratchpad, list):
            scratchpad_items = len(scratchpad)
            scratchpad_tokens = self._estimate_tokens(self._to_text(scratchpad))
        elif isinstance(scratchpad, str):
            scratchpad_items = 1
            scratchpad_tokens = self._estimate_tokens(scratchpad)

        mem = obs.get("memory")
        memory_records = 0
        if isinstance(mem, dict):
            recs = mem.get("records")
            if isinstance(recs, list):
                memory_records = len(recs)

        stats: Dict[str, Any] = {
            "scratchpad_items": scratchpad_items,
            "scratchpad_tokens": scratchpad_tokens,
            "memory_records": memory_records,
        }

        workspace_files = obs.get("workspace_files")
        if isinstance(workspace_files, list):
            stats["workspace_files"] = len(workspace_files)
        return stats

    def memory_summary(self, event: RenderEvent) -> Optional[str]:
        if event.node != "memory_context":
            return None
        payload = event.payload or {}
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        summary = str(payload.get("summary", "")).strip()
        if summary:
            return f"records={len(records)} · {self._truncate(summary, 180)}"
        return f"records={len(records)}"

    def done_summary(self, stop_reason: Any, final_result: Any) -> str:
        return f"stop={stop_reason} · result={self._truncate(self._to_text(final_result), 180)}"

    def _action_from_dict(self, action: Any) -> Dict[str, str]:
        if not isinstance(action, dict):
            return {"label": "ACTION", "detail": self._truncate(self._to_text(action), 120), "status": "neutral"}
        name = str(action.get("name") or action.get("tool") or action.get("action") or "action")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        detail = ""
        if args:
            for key in ("query", "url", "path", "command", "prompt", "file"):
                if key in args:
                    detail = self._truncate(self._to_text(args[key]), 120)
                    break
            if not detail:
                k = next(iter(args.keys()))
                detail = self._truncate(f"{k}={self._to_text(args[k])}", 120)
        return {
            "label": name.upper().replace("_", " "),
            "detail": self._compress_detail(detail),
            "status": "neutral",
        }

    def _extract_search_rows(self, data: Any) -> List[Tuple[str, str]]:
        rows: List[Tuple[str, str]] = []
        candidates: List[Any] = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            for key in ("results", "items", "search_results", "web_results", "hits"):
                if isinstance(data.get(key), list):
                    candidates = data.get(key)
                    break
        for item in candidates:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "")
            url = str(item.get("url") or item.get("link") or item.get("href") or "")
            if not title or not url:
                continue
            rows.append((title, self._short_url(url)))
        return rows

    def _extract_syntax(self, data: Dict[str, Any]) -> Optional[Syntax]:
        for key in ("content", "file_content", "source", "text"):
            value = data.get(key)
            if not isinstance(value, str):
                continue
            if "\n" not in value or len(value) < 40:
                continue
            return Syntax(self._truncate(value, 2000), self._guess_language(data), word_wrap=True)
        return None

    def _best_body(self, data: Dict[str, Any]) -> str:
        for key in ("content", "summary", "message", "observation", "text"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
        lite: Dict[str, Any] = {}
        for k, v in data.items():
            if k in _NOISE_KEYS:
                continue
            if isinstance(v, (dict, list)):
                continue
            lite[k] = v
        return self._to_text(lite)

    def _strip_noise(self, data: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in data.items():
            if key in _NOISE_KEYS:
                continue
            if key == "error_category" and value is None:
                continue
            out[key] = value
        return out

    def _guess_language(self, data: Dict[str, Any]) -> str:
        path = str(data.get("path") or data.get("file") or "")
        if path.endswith(".py"):
            return "python"
        if path.endswith(".md"):
            return "markdown"
        if path.endswith(".json"):
            return "json"
        if path.endswith(".sh"):
            return "bash"
        return "text"

    def _short_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            host = parsed.netloc or parsed.path
            path = parsed.path if parsed.netloc else ""
            if len(path) > 24:
                path = path[:24] + "..."
            return f"{host}{path}"
        except Exception:
            return self._truncate(url, 36)

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[:limit]}... (truncated)"

    def _to_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    def _estimate_tokens(self, text: str) -> int:
        # Lightweight estimator for on-screen stats only.
        if not text:
            return 0
        return len(re.findall(r"\w+|[^\s\w]", text, flags=re.UNICODE))

    def _compress_detail(self, detail: str) -> str:
        if not detail:
            return ""
        d = detail.strip()
        if d.startswith("http://") or d.startswith("https://"):
            try:
                parsed = urlparse(d)
                host = parsed.netloc or d
                path = parsed.path or ""
                return self._truncate(f"{host}{path[:16]}", 40)
            except Exception:
                return self._truncate(d, 40)
        return self._truncate(d, 70)


__all__ = ["ContentFirstRenderer"]
