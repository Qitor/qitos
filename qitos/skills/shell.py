"""
Shell Skills

Provides system command execution skills.
"""

import os
import subprocess
from typing import Any, Dict, Optional
from qitos.core.skill import Skill


class RunCommand(Skill):
    """
    System command execution skill
    
    Execute system commands in the specified directory and capture output.
    Supports timeout control and error handling.
    """
    
    def __init__(
        self,
        timeout: int = 30,
        cwd: str = ".",
        env: Optional[Dict[str, str]] = None
    ):
        """
        Initialize RunCommand skill
        
        :param timeout: Command execution timeout (seconds), default 30 seconds
        :param cwd: Working directory for command execution, defaults to current directory
        :param env: Environment variable dictionary, defaults to inheriting current environment
        """
        super().__init__(name="run_command")
        self._timeout = timeout
        self._cwd = os.path.abspath(cwd) if cwd else os.getcwd()
        self._env = env
    
    def run(self, command: str) -> Dict[str, Any]:
        """
        Execute system command and return results
        
        :param command: System command to execute
        
        Returns structured output with command execution status, stdout, stderr and return code
        """
        if not command or not command.strip():
            return {"status": "error", "message": "Command cannot be empty"}
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=self._cwd,
                env=self._env
            )
            
            return {
                "status": "success" if result.returncode == 0 else "partial",
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "cwd": self._cwd
            }
            
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": f"Command execution timeout ({self._timeout}s)",
                "command": command,
                "timeout": self._timeout
            }
        except PermissionError as e:
            return {
                "status": "error",
                "message": f"Permission denied: {str(e)}",
                "command": command
            }
        except FileNotFoundError as e:
            return {
                "status": "error",
                "message": f"Command not found: {str(e)}",
                "command": command
            }
        except OSError as e:
            return {
                "status": "error",
                "message": f"Execution failed: {str(e)}",
                "command": command
            }
