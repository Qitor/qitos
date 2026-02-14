"""
Model Base Classes

Unified LLM calling interface.

Design Principles:
1. All model implementations are callable objects
2. Input: OpenAI-style messages list
3. Output: Text that can be parsed by execution_engine.parse_tool_calls()
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class Model(ABC):
    """
    Unified model calling interface
    
    All model implementations (OpenAI, Ollama, Anthropic, etc.) should inherit from this class.
    
    Interface Contract:
    - Input: OpenAI-style messages list
    - Output: Text format that can be parsed by parse_tool_calls()
    
    Output Format Specification:
    ```
    Action: tool_name(arg1="value1", arg2="value2")
    
    Or
    
    Action 1: search
    "query": "python tutorial"
    
    Or
    
    Final Answer: This is the final answer
    ```
    
    Example:
        llm = OpenAIModel(model="gpt-4")
        result = llm([{"role": "user", "content": "Help me search"}])
        # Returns: "Action: search(query='python tutorial')\n\n"
    """
    
    def __init__(
        self,
        model: str = "default",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ):
        """
        Initialize model
        
        Args:
            model: Model name
            system_prompt: System prompt
            temperature: Temperature parameter (0.0-1.0)
            max_tokens: Maximum output token count
        """
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    @abstractmethod
    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """
        Actually call the model API
        
        Subclasses must implement this method.
        
        Args:
            messages: OpenAI-style messages list
            
        Returns:
            Raw model output text
        """
        pass
    
    def __call__(self, messages: List[Dict[str, str]]) -> str:
        """
        Call model to generate response
        
        Args:
            messages: OpenAI-style messages list
                [{"role": "system", "content": "..."}, ...]
                
        Returns:
            Text that can be parsed by parse_tool_calls()
        """
        return self._call_api(messages)
    
    def format_messages(
        self,
        user_content: str,
        history: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, str]]:
        """
        Format messages (helper method)
        
        Args:
            user_content: User input
            history: Historical messages (observations, etc.)
            
        Returns:
            Formatted messages list
        """
        messages = []
        
        if self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        return messages
    
    def format_tool_response(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any
    ) -> str:
        """
        Format tool response (for multi-turn dialogue)
        
        Args:
            tool_name: Tool name
            args: Tool parameters
            result: Tool execution result
            
        Returns:
            Formatted observation result
        """
        return f"""Observed result from {tool_name}:
{result}

Please decide on the next action, or provide a Final Answer if the task is complete."""
    
    def format_final_answer(self, answer: str) -> str:
        """
        Format final answer
        
        Args:
            answer: Final answer
            
        Returns:
            Final answer in parse_tool_calls compatible format
        """
        return f"Final Answer: {answer}"
    
    def format_action(
        self,
        tool_name: str,
        args: Dict[str, Any]
    ) -> str:
        """
        Format tool call
        
        Args:
            tool_name: Tool name
            args: Tool parameters
            
        Returns:
            Tool call in parse_tool_calls compatible format
        """
        args_str = ", ".join(
            f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
            for k, v in args.items()
        )
        return f"Action: {tool_name}({args_str})"
    
    @property
    def config(self) -> Dict[str, Any]:
        """
        Get model configuration (for debugging)
        """
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system_prompt": self.system_prompt
        }
    
    def __repr__(self) -> str:
        return f"Model(model='{self.model}', temperature={self.temperature})"


class AsyncModel(Model):
    """
    Async model base class
    
    Supports async API calls (e.g., aiohttp, httpx)
    """
    
    @abstractmethod
    async def _acall_api(self, messages: List[Dict[str, str]]) -> str:
        """
        Async call to model API
        
        Subclasses must implement this method.
        """
        pass
    
    async def __call__(self, messages: List[Dict[str, str]]) -> str:
        """
        Async call to model
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._call_api(messages)
        )


class ModelFactory:
    """
    Model factory
    
    Create different types of models based on configuration
    """
    
    _providers = {}
    
    @classmethod
    def register(cls, name: str) -> Callable:
        """Register model provider"""
        def decorator(model_class):
            cls._providers[name] = model_class
            return model_class
        return decorator
    
    @classmethod
    def create(cls, provider: str, **kwargs) -> Model:
        """
        Create model instance
        
        Args:
            provider: Provider identifier ("openai", "ollama", "local", etc.)
            **kwargs: Model configuration parameters
            
        Returns:
            Model instance
            
        Raises:
            ValueError: Unsupported provider
        """
        if provider not in cls._providers:
            raise ValueError(f"Unknown model provider: {provider}")
        
        return cls._providers[provider](**kwargs)
    
    @classmethod
    def from_env(cls, **kwargs) -> Optional[Model]:
        """
        Create model from environment variables
        
        Check environment variables and automatically select appropriate model
        
        Returns:
            Model instance, or None if unable to create
        """
        import os
        
        # Check OpenAI
        if os.getenv("OPENAI_API_KEY"):
            return cls.create("openai", **kwargs)
        
        # Check Ollama
        if os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL"):
            return cls.create("ollama", **kwargs)
        
        return None
