"""Toolset for open deep research style agents (web + long-page navigation + file inspection)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote_plus

from qitos.core.tool import tool
from qitos.kit.tool.web import HTMLExtractText, HTTPGet


@dataclass
class _BrowserState:
    url: str = ""
    title: str = ""
    lines: List[str] = field(default_factory=list)
    cursor: int = 0


class OpenDeepResearchToolSet:
    """Curated toolset inspired by open_deep_research workflow."""

    name = "open_deep_research"
    version = "1.0"

    def __init__(self, workspace_root: str = ".", page_window_lines: int = 40):
        self._workspace_root = os.path.abspath(workspace_root)
        self._page_window_lines = max(10, int(page_window_lines))
        self._http_get = HTTPGet(timeout=40, max_retries=2)
        self._extract = HTMLExtractText()
        self._state = _BrowserState()

    def _resolve_path(self, path: str) -> str:
        root = Path(self._workspace_root).resolve()
        rel = path.lstrip("/")
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)):
            raise PermissionError(f"Path outside workspace: {path}")
        return str(target)

    def _window(self, cursor: int | None = None, lines: int | None = None) -> Dict[str, Any]:
        if not self._state.lines:
            return {"status": "error", "message": "No active page. Call visit_url first."}
        c = self._state.cursor if cursor is None else max(0, int(cursor))
        n = self._page_window_lines if lines is None else max(5, int(lines))
        start = min(c, max(0, len(self._state.lines) - 1))
        end = min(len(self._state.lines), start + n)
        snippet = "\n".join(self._state.lines[start:end])
        self._state.cursor = start
        return {
            "status": "success",
            "url": self._state.url,
            "title": self._state.title,
            "line_start": start,
            "line_end": end,
            "total_lines": len(self._state.lines),
            "content": snippet,
        }

    @tool(name="web_search")
    def web_search(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        """Search web via DuckDuckGo HTML endpoint and return title/url snippets."""
        if not query or not query.strip():
            return {"status": "error", "message": "query cannot be empty"}
        max_results = max(1, min(int(max_results), 20))
        url = f"https://duckduckgo.com/html/?q={quote_plus(query.strip())}"
        resp = self._http_get.run(url=url)
        if resp.get("status") != "success":
            return resp
        html = str(resp.get("content", ""))
        pattern = re.compile(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        rows: list[dict[str, str]] = []
        for href, title_html in pattern.findall(html):
            title = re.sub(r"<[^>]+>", "", title_html)
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            rows.append({"title": title, "url": href})
            if len(rows) >= max_results:
                break
        return {"status": "success", "query": query, "count": len(rows), "results": rows}

    @tool(name="visit_url")
    def visit_url(self, url: str, max_chars: int = 30000) -> Dict[str, Any]:
        """Visit one URL, parse readable text, and cache page for navigation."""
        resp = self._http_get.run(url=url)
        if resp.get("status") != "success":
            return resp
        html = str(resp.get("content", ""))
        extracted = self._extract.run(html=html, max_chars=max_chars, keep_links=True)
        if extracted.get("status") != "success":
            return extracted
        text = str(extracted.get("content", ""))
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        if len(lines) <= 1:
            lines = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        self._state.url = str(resp.get("url", url))
        self._state.title = str(extracted.get("title") or "")
        self._state.lines = lines
        self._state.cursor = 0
        return self._window(cursor=0)

    @tool(name="page_down")
    def page_down(self, lines: int = 40) -> Dict[str, Any]:
        """Move page cursor downward and return next text window."""
        return self._window(cursor=self._state.cursor + int(lines), lines=lines)

    @tool(name="page_up")
    def page_up(self, lines: int = 40) -> Dict[str, Any]:
        """Move page cursor upward and return previous text window."""
        return self._window(cursor=max(0, self._state.cursor - int(lines)), lines=lines)

    @tool(name="find_in_page")
    def find_in_page(self, keyword: str) -> Dict[str, Any]:
        """Find next occurrence of keyword starting from current cursor."""
        if not self._state.lines:
            return {"status": "error", "message": "No active page. Call visit_url first."}
        key = (keyword or "").strip().lower()
        if not key:
            return {"status": "error", "message": "keyword cannot be empty"}
        start = min(self._state.cursor + 1, len(self._state.lines) - 1)
        seq = list(range(start, len(self._state.lines))) + list(range(0, start))
        for idx in seq:
            if key in self._state.lines[idx].lower():
                self._state.cursor = idx
                window = self._window(cursor=idx, lines=self._page_window_lines)
                window["matched_line"] = idx
                return window
        return {"status": "error", "message": f"'{keyword}' not found on current page"}

    @tool(name="inspect_file_as_text")
    def inspect_file_as_text(self, path: str, max_chars: int = 16000) -> Dict[str, Any]:
        """Read local file as text with graceful decoding fallback."""
        try:
            resolved = self._resolve_path(path)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
        if not os.path.exists(resolved):
            return {"status": "error", "message": f"File does not exist: {path}"}
        if os.path.isdir(resolved):
            return {"status": "error", "message": f"Path is a directory: {path}"}
        try:
            with open(resolved, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(resolved, "rb") as f:
                text = f.read().decode("utf-8", errors="ignore")
        if max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        return {"status": "success", "path": path, "size": len(text), "content": text}


__all__ = ["OpenDeepResearchToolSet"]

