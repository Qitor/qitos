"""
Window Memory

Window-based memory implementation, supports sliding window size history retrieval.

v9.0 Simplified version:
- DRY: UnlimitedMemory inherits WindowMemory
- retrieve: Simplified role mapping, only handles user/assistant
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from qitos.core.context import AgentContext

from .base import BaseMemory


class WindowMemory(BaseMemory):
    """
    Logical window memory: Truncates by Agent interaction rounds (Step).
    
    Extraction logic:
    - Only extracts roles within last N Steps.
    - Only collects user and assistant roles (Observation is handled by Agent in gather or included in user).
    """
    
    def __init__(self, window_size: int = 5):
        """
        Args:
            window_size: Keep last N rounds of interaction. 0 means keep all.
        """
        self.window_size = window_size

    def retrieve(self, context: 'AgentContext', **kwargs) -> List[Dict[str, Any]]:
        """Retrieve last N rounds of user/assistant conversation from trajectory"""
        if not context.trajectory:
            return []

        # 1. Determine step truncation threshold
        # Logic: If current is step 10, window is 3, only get records with step > (10 - 3) = 7
        min_step = 0
        if self.window_size > 0:
            min_step = max(0, context.current_step - self.window_size)
        
        messages = []
        # 2. Iterate trajectory, only collect records within window Step and with user/assistant role
        for entry in context.trajectory:
            if entry.step >= min_step:
                if entry.role in ["user", "assistant"]:
                    messages.append({
                        "role": entry.role,
                        "content": entry.content
                    })
        
        return messages

    def __repr__(self) -> str:
        return f"WindowMemory(window_size={self.window_size})"


class SlidingWindowMemory(WindowMemory):
    """Alias for SlidingWindowMemory"""
    pass


class FixedWindowMemory(WindowMemory):
    """
    Fixed window memory
    
    Keep trajectory entries with specified roles.
    """
    pass


class UnlimitedMemory(WindowMemory):
    """Keep all history steps."""
    def __init__(self):
        super().__init__(window_size=0)