"""
Memory Base Classes

Memory module base classes, defines unified memory retrieval interface.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from qitos.core.context import AgentContext


class BaseMemory(ABC):
    """
    Memory base class
    
    Defines interface for retrieving and formatting history messages from AgentContext.
    
    Users can inherit from this class to implement custom memory strategies.
    
    Example:
        class CustomMemory(BaseMemory):
            def retrieve(self, context, **kwargs) -> List[Dict]:
                # Custom logic
                return [...]
    """
    
    @abstractmethod
    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and format history messages from context
        
        Args:
            context: AgentContext instance, containing complete conversation history
            **kwargs: Extra params (e.g. window_size, etc.)
            
        Returns:
            Formatted message list, following OpenAI messages format
        """
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class MemoryMixin(BaseMemory):
    """
    Simplified memory mixin class
    
    Provides basic observations retrieval logic.
    Can be used as base class for custom memory classes.
    """
    
    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]:
        """
        Default implementation: directly convert observations to messages
        
        Args:
            context: AgentContext instance
            
        Returns:
            Message list
        """
        messages = []
        
        for obs in context.observations:
            messages.append({
                "role": "user",
                "content": f"Observation: {obs}"
            })
        
        return messages


class ConversationMemory(BaseMemory):
    """
    Conversation-style memory
    
    Alternates user/assistant roles to record conversation history.
    """
    
    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]:
        """
        Convert observations to conversation format
        
        Assumptions:
        - Tool calls as assistant messages
        - Tool results as user messages (Observation)
        
        Args:
            context: AgentContext instance
            
        Returns:
            Conversation format message list
        """
        messages = []
        
        for i, obs in enumerate(context.observations):
            is_tool_call = isinstance(obs, dict) and obs.get("status") != "error"
            
            role = "assistant" if is_tool_call else "user"
            
            if isinstance(obs, dict):
                content = str(obs)
            else:
                content = str(obs)
            
            messages.append({
                "role": role,
                "content": content
            })
        
        return messages


class SummaryMemory(BaseMemory):
    """
    Summary memory
    
    Only keeps summary of last N messages.
    """
    
    def __init__(self, window_size: int = 3, summary_template: str = None):
        """
        Initialize summary memory
        
        Args:
            window_size: Number of messages to keep
            summary_template: Summary template
        """
        self.window_size = window_size
        self.summary_template = summary_template or "Recent observations: {content}"
    
    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]:
        """
        Generate summary message
        
        Args:
            context: AgentContext instance
            
        Returns:
            Message list containing summary
        """
        recent = context.observations[-self.window_size:] if self.window_size > 0 else []
        
        if not recent:
            return []
        
        content_parts = []
        for obs in recent:
            if isinstance(obs, dict):
                content_parts.append(str(obs))
            else:
                content_parts.append(str(obs))
        
        content = self.summary_template.format(
            content="\n".join(content_parts)
        )
        
        return [{
            "role": "user",
            "content": content
        }]
