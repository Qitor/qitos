"""
OpenAI Model Implementation

OpenAI API-based model calling implementation.
Supports environment variable configuration: OPENAI_API_KEY, OPENAI_BASE_URL
"""

import os
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from .base import Model


class OpenAIModel(Model):
    """
    OpenAI model calling implementation
    
    Environment variable configuration:
    - OPENAI_API_KEY: OpenAI API key
    - OPENAI_BASE_URL: OpenAI API base URL (optional, default https://api.openai.com/v1)
    
    Output format:
    - If model returns tool_calls: Convert to "Action: tool_name(args)" format
    - If model returns content: Return directly
    - Supports function calling format
    
    Example:
        llm = OpenAIModel(model="gpt-4")
        result = llm([{"role": "user", "content": "Help me search for Python tutorials"}])
        # Returns: "Action: search(query='Python tutorials')"
    """
    
    def __init__(
        self,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60
    ):
        """
        Initialize OpenAI model
        
        Args:
            model: Model name, default gpt-4
            api_key: API key, default read from environment variable
            base_url: API base URL, default read from environment variable
            system_prompt: System prompt
            temperature: Temperature parameter (0.0-1.0)
            max_tokens: Maximum output token count
            timeout: Request timeout (seconds)
        """
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.timeout = timeout
        
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. Please set environment variable or pass api_key parameter."
            )
    
    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """
        Call OpenAI API
        
        Args:
            messages: OpenAI-style messages list
            
        Returns:
            Text that can be parsed by parse_tool_calls()
        """
        import openai
        
        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return self._parse_response(response)
            
        except openai.APIError as e:
            return f"API Error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _parse_response(self, response) -> str:
        """
        Parse OpenAI response and convert to target format
        
        Args:
            response: OpenAI API response object
            
        Returns:
            Text in parse_tool_calls compatible format
        """
        choice = response.choices[0]
        message = choice.message
        
        # Prioritize processing tool_calls
        if message.tool_calls:
            return self._format_tool_calls(message.tool_calls)
        
        # Return content
        if message.content:
            return message.content.strip()
        
        return ""
    
    def _format_tool_calls(self, tool_calls) -> str:
        """
        Convert OpenAI tool_calls format to parse_tool_calls compatible format
        
        Args:
            tool_calls: OpenAI tool_calls list
            
        Returns:
            Formatted tool call text
        """
        parts = []
        
        for i, call in enumerate(tool_calls):
            function = call.function
            name = function.name
            args = function.arguments
            
            try:
                args_dict = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args_dict = {"raw_args": args}
            
            if len(tool_calls) > 1:
                parts.append(f"Action {i + 1}: {name}")
            else:
                parts.append(f"Action: {name}")
            
            if args_dict:
                args_str = ", ".join(
                    f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                    for k, v in args_dict.items()
                )
                parts[-1] += f"({args_str})"
        
        return "\n".join(parts)


class OpenAICompatibleModel(Model):
    """
    OpenAI compatible interface model
    
    Supports any service compatible with OpenAI API format, such as:
    - Azure OpenAI
    - Anthropic (via compatible endpoints)
    - LM Studio
    - LocalAI
    - Tongyi Qianwen
    - Zhipu AI
    
    Example:
        llm = OpenAICompatibleModel(
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
    """
    
    def __init__(
        self,
        model: str = "default",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60
    ):
        """
        Initialize compatible model
        
        Args:
            model: Model name
            api_key: API key
            base_url: API base URL
            system_prompt: System prompt
            temperature: Temperature parameter
            max_tokens: Maximum output token count
            timeout: Request timeout
        """
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or "dummy-key"
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "")
        self.timeout = timeout
        
        if not self.base_url:
            raise ValueError(
                "OPENAI_BASE_URL not set. Please set environment variable or pass base_url parameter."
            )
    
    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """
        Call OpenAI compatible API
        
        Args:
            messages: OpenAI-style messages list
            
        Returns:
            Text that can be parsed by parse_tool_calls()
        """
        import openai
        
        try:
            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return self._parse_response(response)
            
        except openai.APIError as e:
            return f"API Error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _parse_response(self, response) -> str:
        """
        Parse response
        """
        choice = response.choices[0]
        message = choice.message
        
        if message.tool_calls:
            return self._format_tool_calls(message.tool_calls)
        
        if message.content:
            return message.content.strip()
        
        return ""
    
    def _format_tool_calls(self, tool_calls) -> str:
        """
        Format tool calls
        """
        import json
        
        parts = []
        
        for i, call in enumerate(tool_calls):
            function = call.function
            name = function.name
            args = function.arguments or "{}"
            
            try:
                args_dict = json.loads(args)
            except json.JSONDecodeError:
                args_dict = {"raw": args}
            
            if len(tool_calls) > 1:
                parts.append(f"Action {i + 1}: {name}")
            else:
                parts.append(f"Action: {name}")
            
            if args_dict:
                args_str = ", ".join(
                    f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                    for k, v in args_dict.items()
                )
                parts[-1] += f"({args_str})"
        
        return "\n".join(parts)


class AzureOpenAIModel(OpenAICompatibleModel):
    """
    Azure OpenAI model implementation
    
    Specifically optimized for Azure OpenAI service
    
    Environment variable configuration:
    - AZURE_OPENAI_API_KEY: Azure API key
    - AZURE_OPENAI_ENDPOINT: Azure endpoint URL
    - AZURE_OPENAI_DEPLOYMENT: Deployment name
    - AZURE_OPENAI_API_VERSION: API version (default 2024-02-15-preview)
    
    Example:
        llm = AzureOpenAIModel(
            deployment="gpt-4",
            api_version="2024-02-15-preview"
        )
    """
    
    def __init__(
        self,
        deployment: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-02-15-preview",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60
    ):
        """
        Initialize Azure OpenAI model
        
        Args:
            deployment: Deployment name (used as model)
            api_key: API key, default read from environment variable
            endpoint: Endpoint URL, default read from environment variable
            api_version: API version
            system_prompt: System prompt
            temperature: Temperature parameter
            max_tokens: Maximum output token count
            timeout: Request timeout
        """
        api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        
        if not endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT not set. Please set environment variable or pass endpoint parameter."
            )
        
        base_url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment or 'default'}"
        
        super().__init__(
            model=deployment or "azure",
            api_key=api_key,
            base_url=base_url,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )
        
        self.api_version = api_version
        self.deployment = deployment
        self.endpoint = endpoint
    
    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """
        Call Azure OpenAI API (adds api_version parameter)
        """
        import openai
        
        try:
            client = openai.AzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.endpoint,
                api_version=self.api_version,
                timeout=self.timeout
            )
            
            response = client.chat.completions.create(
                model=self.deployment or "",
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return self._parse_response(response)
            
        except openai.APIError as e:
            return f"API Error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"


# Register to factory
from .base import ModelFactory

ModelFactory.register("openai")(OpenAIModel)
ModelFactory.register("azure")(AzureOpenAIModel)
ModelFactory.register("openai-compatible")(OpenAICompatibleModel)
