"""
File Operations Skills

Provides basic file operation skills such as read, write, and list.
"""

import os
from typing import Any, Dict, List, Optional
from qitos.core.skill import Skill


class WriteFile(Skill):
    """
    File write skill
    
    Safely create or overwrite files in the specified directory.
    All paths undergo security validation to prevent directory traversal attacks.
    """
    
    def __init__(self, root_dir: str = "."):
        """
        Initialize WriteFile skill
        
        :param root_dir: Root directory for file writes, defaults to current directory
        """
        super().__init__(name="write_file")
        self._root_dir = os.path.abspath(root_dir)
    
    def run(self, filename: str, content: str) -> Dict[str, Any]:
        """
        Write content to specified file
        
        :param filename: Filename to write (relative to root_dir)
        :param content: File content to write
        
        Returns structured output with file path and status
        """
        if not filename:
            return {"status": "error", "message": "Filename cannot be empty"}
        
        safe_path = os.path.abspath(os.path.join(self._root_dir, filename))
        
        if not safe_path.startswith(self._root_dir):
            return {"status": "error", "message": "Access to files outside directory is prohibited"}
        
        try:
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {
                "status": "success",
                "path": safe_path,
                "size": len(content)
            }
        except PermissionError as e:
            return {"status": "error", "message": f"Permission denied: {str(e)}"}
        except OSError as e:
            return {"status": "error", "message": f"Write failed: {str(e)}"}


class ReadFile(Skill):
    """
    File read skill
    
    Safely read content from specified file.
    All paths undergo security validation to prevent directory traversal attacks.
    """
    
    def __init__(self, root_dir: str = "."):
        """
        Initialize ReadFile skill
        
        :param root_dir: Root directory for file reads, defaults to current directory
        """
        super().__init__(name="read_file")
        self._root_dir = os.path.abspath(root_dir)
    
    def run(self, filename: str) -> Dict[str, Any]:
        """
        Read content from specified file
        
        :param filename: Filename to read (relative to root_dir)
        
        Returns structured output with file content and metadata
        """
        if not filename:
            return {"status": "error", "message": "Filename cannot be empty"}
        
        safe_path = os.path.abspath(os.path.join(self._root_dir, filename))
        
        if not safe_path.startswith(self._root_dir):
            return {"status": "error", "message": "Access to files outside directory is prohibited"}
        
        if not os.path.exists(safe_path):
            return {"status": "error", "message": f"File does not exist: {filename}"}
        
        if os.path.isdir(safe_path):
            return {"status": "error", "message": "This is a directory, not a file"}
        
        try:
            with open(safe_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "status": "success",
                "content": content,
                "path": safe_path,
                "size": len(content)
            }
        except UnicodeDecodeError:
            return {"status": "error", "message": "File encoding does not support UTF-8"}
        except PermissionError as e:
            return {"status": "error", "message": f"Permission denied: {str(e)}"}
        except OSError as e:
            return {"status": "error", "message": f"Read failed: {str(e)}"}


class ListFiles(Skill):
    """
    File list skill
    
    List all files and subdirectories in the specified directory.
    All paths undergo security validation to prevent directory traversal attacks.
    """
    
    def __init__(self, root_dir: str = "."):
        """
        Initialize ListFiles skill
        
        :param root_dir: Root directory for listing files, defaults to current directory
        """
        super().__init__(name="list_files")
        self._root_dir = os.path.abspath(root_dir)
    
    def run(self, path: str = ".") -> Dict[str, Any]:
        """
        List all files and subdirectories in the specified directory
        
        :param path: Directory path to list (relative to root_dir), defaults to current directory
        
        Returns structured output with file list and metadata
        """
        target_path = os.path.abspath(os.path.join(self._root_dir, path))
        
        if not target_path.startswith(self._root_dir):
            return {"status": "error", "message": "Access to files outside directory is prohibited"}
        
        if not os.path.exists(target_path):
            return {"status": "error", "message": f"Path does not exist: {path}"}
        
        if not os.path.isdir(target_path):
            return {"status": "error", "message": "This is not a directory"}
        
        try:
            items = []
            for item in os.listdir(target_path):
                item_path = os.path.join(target_path, item)
                items.append({
                    "name": item,
                    "type": "directory" if os.path.isdir(item_path) else "file",
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else None
                })
            
            items.sort(key=lambda x: (x["type"] == "file", x["name"]))
            
            return {
                "status": "success",
                "path": target_path,
                "count": len(items),
                "files": items
            }
        except PermissionError as e:
            return {"status": "error", "message": f"Permission denied: {str(e)}"}
        except OSError as e:
            return {"status": "error", "message": f"List failed: {str(e)}"}
