"""File-oriented concrete tool objects."""

from __future__ import annotations

import os
from typing import Any, Dict

from qitos.core.tool import BaseTool, ToolPermission, ToolSpec


class WriteFile(BaseTool):
    def __init__(self, root_dir: str = "."):
        self._root_dir = os.path.abspath(root_dir)
        super().__init__(
            ToolSpec(
                name="write_file",
                description="Write content to a file under workspace",
                parameters={"filename": {"type": "string"}, "content": {"type": "string"}},
                required=["filename", "content"],
                permissions=ToolPermission(filesystem_write=True),
                required_ops=["file"],
            )
        )

    def run(self, filename: str, content: str, runtime_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        runtime_context = runtime_context or {}
        ops = runtime_context.get("ops", {})
        file_ops = ops.get("file")
        if file_ops is not None and hasattr(file_ops, "write_text"):
            try:
                file_ops.write_text(filename, content)
                return {"status": "success", "path": filename, "size": len(content)}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        if not filename:
            return {"status": "error", "message": "Filename cannot be empty"}
        safe_path = os.path.abspath(os.path.join(self._root_dir, filename))
        if not safe_path.startswith(self._root_dir):
            return {"status": "error", "message": "Access to files outside directory is prohibited"}
        try:
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"status": "success", "path": safe_path, "size": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class ReadFile(BaseTool):
    def __init__(self, root_dir: str = "."):
        self._root_dir = os.path.abspath(root_dir)
        super().__init__(
            ToolSpec(
                name="read_file",
                description="Read file content under workspace",
                parameters={"filename": {"type": "string"}},
                required=["filename"],
                permissions=ToolPermission(filesystem_read=True),
                required_ops=["file"],
            )
        )

    def run(self, filename: str, runtime_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        runtime_context = runtime_context or {}
        ops = runtime_context.get("ops", {})
        file_ops = ops.get("file")
        if file_ops is not None and hasattr(file_ops, "read_text"):
            try:
                content = file_ops.read_text(filename)
                return {"status": "success", "content": content, "path": filename, "size": len(content)}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        if not filename:
            return {"status": "error", "message": "Filename cannot be empty"}
        safe_path = os.path.abspath(os.path.join(self._root_dir, filename))
        if not safe_path.startswith(self._root_dir):
            return {"status": "error", "message": "Access to files outside directory is prohibited"}
        try:
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "success", "content": content, "path": safe_path, "size": len(content)}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class ListFiles(BaseTool):
    def __init__(self, root_dir: str = "."):
        self._root_dir = os.path.abspath(root_dir)
        super().__init__(
            ToolSpec(
                name="list_files",
                description="List files and directories under workspace",
                parameters={"path": {"type": "string"}},
                required=[],
                permissions=ToolPermission(filesystem_read=True),
                required_ops=["file"],
            )
        )

    def run(self, path: str = ".", runtime_context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        runtime_context = runtime_context or {}
        ops = runtime_context.get("ops", {})
        file_ops = ops.get("file")
        if file_ops is not None and hasattr(file_ops, "list_files"):
            try:
                files = file_ops.list_files(path=path)
                return {"status": "success", "path": path, "count": len(files), "files": files}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        target_path = os.path.abspath(os.path.join(self._root_dir, path))
        if not target_path.startswith(self._root_dir):
            return {"status": "error", "message": "Access to files outside directory is prohibited"}
        try:
            items = []
            for item in os.listdir(target_path):
                item_path = os.path.join(target_path, item)
                items.append(
                    {
                        "name": item,
                        "type": "directory" if os.path.isdir(item_path) else "file",
                        "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None,
                    }
                )
            items.sort(key=lambda x: (x["type"] == "file", x["name"]))
            return {"status": "success", "path": target_path, "count": len(items), "files": items}
        except Exception as e:
            return {"status": "error", "message": str(e)}


__all__ = ["WriteFile", "ReadFile", "ListFiles"]
