"""Atomic browser tools backed by TextWebEnv web_browser ops."""

from __future__ import annotations

from typing import Any, Dict, Optional

from qitos.core.tool import BaseTool, ToolPermission, ToolSpec


class _WebBrowserTool(BaseTool):
    required_ops = ["web_browser"]

    def _ops(self, runtime_context: Optional[Dict[str, Any]]) -> Any:
        runtime_context = runtime_context or {}
        ops = runtime_context.get("ops", {})
        browser = ops.get("web_browser")
        if browser is None:
            raise ValueError("Missing required ops group: web_browser")
        return browser


class WebSearch(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="web_search",
                description="Search the web and return top text results",
                parameters={"query": {"type": "string"}, "max_results": {"type": "integer"}},
                required=["query"],
                permissions=ToolPermission(network=True),
                required_ops=self.required_ops,
            )
        )

    def run(self, query: str, max_results: int = 8, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).search(query=query, max_results=max_results)


class VisitURL(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="visit_url",
                description="Visit URL and load readable text into browser state",
                parameters={"url": {"type": "string"}, "max_chars": {"type": "integer"}},
                required=["url"],
                permissions=ToolPermission(network=True),
                required_ops=self.required_ops,
            )
        )

    def run(self, url: str, max_chars: int = 30000, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).visit(url=url, max_chars=max_chars)


class PageDown(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="page_down",
                description="Move text page cursor down",
                parameters={"lines": {"type": "integer"}},
                required=[],
                permissions=ToolPermission(),
                required_ops=self.required_ops,
            )
        )

    def run(self, lines: int = 40, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).page_down(lines=lines)


class PageUp(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="page_up",
                description="Move text page cursor up",
                parameters={"lines": {"type": "integer"}},
                required=[],
                permissions=ToolPermission(),
                required_ops=self.required_ops,
            )
        )

    def run(self, lines: int = 40, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).page_up(lines=lines)


class FindInPage(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="find_in_page",
                description="Find keyword in current page and move cursor",
                parameters={"keyword": {"type": "string"}},
                required=["keyword"],
                permissions=ToolPermission(),
                required_ops=self.required_ops,
            )
        )

    def run(self, keyword: str, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).find(keyword=keyword)


class FindNext(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="find_next",
                description="Find next match for previous keyword on page",
                parameters={},
                required=[],
                permissions=ToolPermission(),
                required_ops=self.required_ops,
            )
        )

    def run(self, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).find_next()


class ArchiveSearch(_WebBrowserTool):
    def __init__(self):
        super().__init__(
            ToolSpec(
                name="archive_search",
                description="Search the web archive for historical pages",
                parameters={"query": {"type": "string"}, "max_results": {"type": "integer"}},
                required=["query"],
                permissions=ToolPermission(network=True),
                required_ops=self.required_ops,
            )
        )

    def run(self, query: str, max_results: int = 8, runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ops(runtime_context).archive_search(query=query, max_results=max_results)


__all__ = [
    "WebSearch",
    "VisitURL",
    "PageDown",
    "PageUp",
    "FindInPage",
    "FindNext",
    "ArchiveSearch",
]

