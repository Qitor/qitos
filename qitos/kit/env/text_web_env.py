"""Text web browsing environment with stateful page navigation ops."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from qitos.core.env import EnvObservation
from qitos.kit.env.host_env import HostEnv

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]


@dataclass
class _PageState:
    url: str = ""
    title: str = ""
    lines: List[str] = field(default_factory=list)
    cursor: int = 0
    last_find: str = ""
    last_match: int = -1


class TextWebBrowserOps:
    """Stateful web browser operations for text-first navigation."""

    def __init__(self, timeout: int = 40, page_window_lines: int = 40, user_agent: str = "QitOS-TextWeb/1.0"):
        self.timeout = int(timeout)
        self.page_window_lines = max(10, int(page_window_lines))
        self.user_agent = user_agent
        self.state = _PageState()

    def reset(self) -> None:
        self.state = _PageState()

    def search(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        if requests is None:
            return {"status": "error", "message": "requests is not available"}
        if not query or not query.strip():
            return {"status": "error", "message": "query cannot be empty"}
        max_results = max(1, min(int(max_results), 20))
        url = f"https://duckduckgo.com/html/?q={quote_plus(query.strip())}"
        try:
            r = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=self.timeout)
            html = r.text
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
        pattern = re.compile(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        rows: list[dict[str, str]] = []
        for href, title_html in pattern.findall(html):
            title = re.sub(r"<[^>]+>", "", title_html)
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                rows.append({"title": title, "url": href})
            if len(rows) >= max_results:
                break
        return {"status": "success", "query": query, "count": len(rows), "results": rows}

    def visit(self, url: str, max_chars: int = 30000, keep_links: bool = True) -> Dict[str, Any]:
        if requests is None:
            return {"status": "error", "message": "requests is not available"}
        try:
            r = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=self.timeout)
            text, title = self._html_to_text(r.text, keep_links=keep_links)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

        if max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars] + "\n... [truncated]"
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        if len(lines) <= 1:
            lines = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        self.state.url = str(r.url)
        self.state.title = title or ""
        self.state.lines = lines
        self.state.cursor = 0
        self.state.last_find = ""
        self.state.last_match = -1
        return self.window(cursor=0, lines=self.page_window_lines)

    def page_down(self, lines: int = 40) -> Dict[str, Any]:
        return self.window(cursor=self.state.cursor + int(lines), lines=lines)

    def page_up(self, lines: int = 40) -> Dict[str, Any]:
        return self.window(cursor=max(0, self.state.cursor - int(lines)), lines=lines)

    def find(self, keyword: str) -> Dict[str, Any]:
        if not self.state.lines:
            return {"status": "error", "message": "no active page; call visit_url first"}
        key = (keyword or "").strip().lower()
        if not key:
            return {"status": "error", "message": "keyword cannot be empty"}
        start = self.state.cursor
        for idx in range(start, len(self.state.lines)):
            if key in self.state.lines[idx].lower():
                self.state.cursor = idx
                self.state.last_find = keyword
                self.state.last_match = idx
                out = self.window(cursor=idx, lines=self.page_window_lines)
                out["matched_line"] = idx
                return out
        self.state.last_find = keyword
        self.state.last_match = -1
        return {"status": "error", "message": f"'{keyword}' not found on page"}

    def find_next(self) -> Dict[str, Any]:
        key = (self.state.last_find or "").strip().lower()
        if not key:
            return {"status": "error", "message": "no active keyword; call find_in_page first"}
        start = max(self.state.last_match + 1, 0)
        for idx in range(start, len(self.state.lines)):
            if key in self.state.lines[idx].lower():
                self.state.cursor = idx
                self.state.last_match = idx
                out = self.window(cursor=idx, lines=self.page_window_lines)
                out["matched_line"] = idx
                return out
        return {"status": "error", "message": f"no further match for '{self.state.last_find}'"}

    def archive_search(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        return self.search(f"site:web.archive.org {query}", max_results=max_results)

    def window(self, cursor: int | None = None, lines: int | None = None) -> Dict[str, Any]:
        if not self.state.lines:
            return {"status": "error", "message": "no active page; call visit_url first"}
        c = self.state.cursor if cursor is None else max(0, int(cursor))
        n = self.page_window_lines if lines is None else max(5, int(lines))
        start = min(c, max(0, len(self.state.lines) - 1))
        end = min(len(self.state.lines), start + n)
        self.state.cursor = start
        content = "\n".join(self.state.lines[start:end])
        return {
            "status": "success",
            "url": self.state.url,
            "title": self.state.title,
            "line_start": start,
            "line_end": end,
            "total_lines": len(self.state.lines),
            "content": content,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "active_url": self.state.url,
            "title": self.state.title,
            "cursor": self.state.cursor,
            "total_lines": len(self.state.lines),
            "last_find": self.state.last_find,
            "last_match": self.state.last_match,
        }

    def _html_to_text(self, html: str, keep_links: bool = True) -> tuple[str, Optional[str]]:
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
                tag.decompose()
            if keep_links:
                for a in soup.find_all("a"):
                    href = a.get("href")
                    if href:
                        a.append(f" ({href})")
            title = str(soup.title.string).strip() if soup.title and soup.title.string else None
            text = soup.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip(), title
        data = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        data = re.sub(r"(?is)<style.*?>.*?</style>", " ", data)
        data = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", data)
        title = None
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", data)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        data = re.sub(r"(?is)<[^>]+>", " ", data)
        data = re.sub(r"\s+", " ", data)
        return data.strip(), title


class TextWebEnv(HostEnv):
    """HostEnv + text web browser ops group."""

    name = "text_web_env"
    version = "1.0"

    def __init__(self, workspace_root: str = ".", timeout: int = 40, page_window_lines: int = 40):
        super().__init__(workspace_root=workspace_root)
        self.web_browser = TextWebBrowserOps(timeout=timeout, page_window_lines=page_window_lines)

    def reset(self, task: Any = None, workspace: Optional[str] = None, **kwargs: Any) -> EnvObservation:
        obs = super().reset(task=task, workspace=workspace, **kwargs)
        self.web_browser.reset()
        obs.data["web"] = self.web_browser.summary()
        return obs

    def observe(self, state: Any = None) -> EnvObservation:
        obs = super().observe(state=state)
        obs.data["web"] = self.web_browser.summary()
        return obs

    def get_ops(self, group: str) -> Any:
        if group == "web_browser":
            return self.web_browser
        return super().get_ops(group)


__all__ = ["TextWebBrowserOps", "TextWebEnv"]

