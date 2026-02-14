"""
Web Skills

Provides HTTP request skills, supports async network requests.
"""

import asyncio
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from qitos.core.skill import Skill


class HTTPGet(Skill):
    """
    HTTP GET request skill (async)
    
    Implements async HTTP GET requests using aiohttp.
    Supports query parameters, header settings, and timeout control.
    """
    
    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        user_agent: str = "QitOS-Agent/1.0"
    ):
        """
        Initialize HTTPGet skill
        
        :param headers: HTTP request headers dictionary
        :param timeout: Request timeout (seconds), default 30 seconds
        :param user_agent: Default User-Agent
        """
        super().__init__(name="http_get")
        self._headers = headers or {}
        self._headers.setdefault("User-Agent", user_agent)
        self._timeout = aiohttp.ClientTimeout(total=timeout) if HAS_AIOHTTP else timeout
    
    async def run(self, url: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Send async HTTP GET request
        
        :param url: Request URL address
        :param params: URL query parameters dictionary
        
        Returns structured output with response status, content and metadata
        """
        if not url:
            return {"status": "error", "message": "URL cannot be empty"}
        
        parsed = urlparse(url)
        if not parsed.scheme:
            return {"status": "error", "message": "Invalid URL format"}
        
        if not HAS_AIOHTTP:
            return {
                "status": "error",
                "message": "aiohttp library required",
                "hint": "Please run: pip install aiohttp"
            }
        
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.get(
                    url,
                    params=params,
                    headers=self._headers,
                    allow_redirects=True
                ) as response:
                    
                    text = await response.text()
                    
                    return {
                        "status": "success" if response.status < 400 else "error",
                        "url": str(response.url),
                        "original_url": url,
                        "status_code": response.status,
                        "reason": response.reason,
                        "headers": dict(response.headers),
                        "content_length": len(text),
                        "content": text,
                        "content_type": response.content_type
                    }
                    
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "message": f"Request timeout ({self._timeout}s)",
                "url": url
            }
        except aiohttp.ClientError as e:
            return {
                "status": "error",
                "message": f"Request failed: {str(e)}",
                "url": url
            }
        except OSError as e:
            return {
                "status": "error",
                "message": f"Network error: {str(e)}",
                "url": url
            }


class HTTPPost(Skill):
    """
    HTTP POST request skill (async)
    
    Implements async HTTP POST requests using aiohttp.
    Supports JSON data submission, form data, and file upload.
    """
    
    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        user_agent: str = "QitOS-Agent/1.0"
    ):
        """
        Initialize HTTPPost skill
        
        :param headers: HTTP request headers dictionary
        :param timeout: Request timeout (seconds), default 30 seconds
        :param user_agent: Default User-Agent
        """
        super().__init__(name="http_post")
        self._headers = headers or {}
        self._headers.setdefault("User-Agent", user_agent)
        self._timeout = aiohttp.ClientTimeout(total=timeout) if HAS_AIOHTTP else timeout
    
    async def run(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send async HTTP POST request
        
        :param url: Request URL address
        :param data: Form data dictionary
        :param json_data: JSON data dictionary (Content-Type will be set automatically)
        :param content_type: Manually specify Content-Type
        
        Returns structured output with response status, content and metadata
        """
        if not url:
            return {"status": "error", "message": "URL cannot be empty"}
        
        parsed = urlparse(url)
        if not parsed.scheme:
            return {"status": "error", "message": "Invalid URL format"}
        
        if not HAS_AIOHTTP:
            return {
                "status": "error",
                "message": "aiohttp library required",
                "hint": "Please run: pip install aiohttp"
            }
        
        try:
            headers = dict(self._headers)
            
            if json_data is not None:
                import json
                data = json.dumps(json_data)
                headers.setdefault("Content-Type", "application/json")
            elif data is not None and content_type is None:
                headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            elif content_type:
                headers["Content-Type"] = content_type
            
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(
                    url,
                    data=data,
                    headers=headers,
                    allow_redirects=True
                ) as response:
                    
                    text = await response.text()
                    
                    return {
                        "status": "success" if response.status < 400 else "error",
                        "url": str(response.url),
                        "original_url": url,
                        "status_code": response.status,
                        "reason": response.reason,
                        "headers": dict(response.headers),
                        "content_length": len(text),
                        "content": text,
                        "content_type": response.content_type
                    }
                    
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "message": f"Request timeout ({self._timeout}s)",
                "url": url
            }
        except aiohttp.ClientError as e:
            return {
                "status": "error",
                "message": f"Request failed: {str(e)}",
                "url": url
            }
        except OSError as e:
            return {
                "status": "error",
                "message": f"Network error: {str(e)}",
                "url": url
            }
