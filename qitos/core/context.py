"""
AgentContext: All-knowing state container

v7.0 Trajectory version, establishes structured interaction trajectory.

Core features:
- Dot Access: Supports ctx.task and ctx["task"]
- Mutation Logging: Auto-records all state changes
- Trajectory: Structured interaction trajectory, supports role categorization
- Serialization: Supports to_json/from_json
"""

import json
import copy
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class MutationLog:
    """Record state change log entry"""
    
    def __init__(self, step: int, key: str, old_value: Any, new_value: Any):
        self.timestamp = datetime.now().isoformat()
        self.step = step
        self.key = key
        self.old_value = old_value
        self.new_value = new_value
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "step": self.step,
            "key": self.key,
            "old_value": self._serialize_value(self.old_value),
            "new_value": self._serialize_value(self.new_value)
        }
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize value, avoid circular references for complex objects"""
        try:
            return copy.deepcopy(value)
        except Exception:
            return repr(value)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MutationLog':
        log = cls(
            step=data["step"],
            key=data["key"],
            old_value=data["old_value"],
            new_value=data["new_value"]
        )
        log.timestamp = data.get("timestamp", "")
        return log


class TrajectoryEntry:
    """
    Trajectory entry
    
    Records structured interaction trajectory, supports multiple roles:
    - user: User input
    - assistant: LLM raw response
    - action: Tool call
    - observation: Tool execution result
    """
    
    def __init__(
        self,
        role: str,
        content: Any,
        step: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.timestamp = datetime.now().isoformat()
        self.role = role
        self.content = content
        self.step = step
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self._serialize_content(),
            "step": self.step,
            "metadata": copy.deepcopy(self.metadata)
        }
    
    def _serialize_content(self) -> Any:
        """Serialize content"""
        if isinstance(self.content, (str, int, float, bool, type(None))):
            return self.content
        try:
            return copy.deepcopy(self.content)
        except Exception:
            return repr(self.content)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrajectoryEntry':
        entry = cls(
            role=data["role"],
            content=data["content"],
            step=data.get("step", 0),
            metadata=data.get("metadata", {})
        )
        entry.timestamp = data.get("timestamp", "")
        return entry


class AgentContext(OrderedDict):
    """
    The single state container for Agent.
    
    All state changes must happen here and will be auto-recorded.
    
    Core fields:
        - task: str                    # Original task
        - current_step: int            # Current step (starts from 0)
        - max_steps: int               # Max step limit
        - trajectory: List[TrajectoryEntry]  # Structured interaction trajectory
        - _final_result: str           # Final answer
        - metadata: dict               # User-defined field space
        - _mutation_log: List[MutationLog]  # Auto-recorded change log
    
    Example:
        ctx = AgentContext("Order takeout", max_steps=5)
        ctx["user_location"] = "Beijing"
        print(ctx.user_location)  # "Beijing"
        print(ctx.mutation_log)   # View all change records
    """
    
    def __init__(
        self, 
        task: str, 
        max_steps: int = 10, 
        memory_window: int = 5,
        **kwargs
    ):
        super().__init__()
        
        OrderedDict.__setitem__(self, "_mutation_log", [])
        OrderedDict.__setitem__(self, "task", task)
        OrderedDict.__setitem__(self, "current_step", 0)
        OrderedDict.__setitem__(self, "max_steps", max_steps)
        OrderedDict.__setitem__(self, "trajectory", [])
        OrderedDict.__setitem__(self, "_final_result", None)
        OrderedDict.__setitem__(self, "_memory_window", memory_window)
        OrderedDict.__setitem__(self, "metadata", kwargs)
        OrderedDict.__setitem__(self, "last_obs", [])
        OrderedDict.__setitem__(self, "plan", [])
        OrderedDict.__setitem__(self, "plan_cursor", 0)
        OrderedDict.__setitem__(self, "plan_status", "idle")
    
    @property
    def task(self) -> str:
        """Get original task"""
        return self.get("task", "")
    
    @property
    def current_step(self) -> int:
        """Get current step"""
        return self.get("current_step", 0)
    
    @property
    def trajectory(self) -> List[TrajectoryEntry]:
        """Get trajectory list"""
        return self.get("trajectory", [])
    
    @property
    def metadata(self) -> Dict[str, Any]:
        """Get user-defined metadata"""
        return self.get("metadata", {})
    
    @property
    def mutation_log(self) -> List[MutationLog]:
        """Get all state change logs"""
        return self.get("_mutation_log", [])
    
    @property
    def memory_window(self) -> int:
        """Get memory window size"""
        return self.get("_memory_window", 5)
    
    @memory_window.setter
    def memory_window(self, value: int):
        """Set memory window size"""
        self["_memory_window"] = value
    
    @property
    def final_result(self) -> Optional[str]:
        """Get final answer"""
        return self.get("_final_result")
    
    @final_result.setter
    def final_result(self, value: str):
        """Set final answer"""
        self["_final_result"] = value
    
    @property
    def last_obs(self) -> List[Dict]:
        """Get last observation result list"""
        return self.get("last_obs", [])
    
    @last_obs.setter
    def last_obs(self, value: List[Dict]):
        """Set last observation result list"""
        self["last_obs"] = value
    
    def push_observation(self, observation: Any) -> None:
        """
        Push observation result to context
        
        Args:
            observation: Observation result
        """
        current = self.get("observations", [])
        current.append(observation)
        self["observations"] = current
    
    def set_plan(self, steps: List[str]) -> None:
        """
        Set the plan steps
        
        Args:
            steps: List of step strings
        """
        self["plan"] = steps
        self["plan_cursor"] = 0
        self["plan_status"] = "executing"
    
    def current_plan_step(self) -> Optional[str]:
        """
        Get the current plan step
        
        Returns:
            Current step string or None if plan is empty/finished
        """
        plan = self.get("plan", [])
        cursor = self.get("plan_cursor", 0)
        
        if not plan or cursor >= len(plan):
            return None
        
        return plan[cursor]
    
    def advance_plan(self) -> None:
        """
        Advance to the next plan step
        """
        cursor = self.get("plan_cursor", 0)
        plan = self.get("plan", [])
        
        self["plan_cursor"] = cursor + 1
        
        if cursor + 1 >= len(plan):
            self["plan_status"] = "completed"
    
    def is_planned(self) -> bool:
        """
        Check if plan has items and is not idle
        
        Returns:
            True if plan has items and plan_status is not 'idle'
        """
        plan = self.get("plan", [])
        status = self.get("plan_status", "idle")
        
        return len(plan) > 0 and status != "idle"
    
    def __setitem__(self, key: str, value: Any):
        """Set attribute value, auto-record change log"""
        current_step = self.get("current_step", 0)
        
        if key not in ["_mutation_log", "trajectory"]:
            old_value = self.get(key)
            mutation = MutationLog(
                step=current_step,
                key=key,
                old_value=old_value,
                new_value=value
            )
            OrderedDict.__setitem__(self, "_mutation_log", 
                OrderedDict.__getitem__(self, "_mutation_log") + [mutation])
        
        super().__setitem__(key, value)
    
    def __getitem__(self, key: str) -> Any:
        """Get attribute value"""
        return super().__getitem__(key)
    
    def __getattr__(self, name: str) -> Any:
        """
        Support dot access for metadata fields.
        
        Example:
            ctx.metadata["user_location"] = "Beijing"
            print(ctx.user_location)  # "Beijing"
        """
        if name.startswith("_"):
            try:
                return super().__getitem__(name)
            except KeyError:
                raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        
        metadata = self.get("metadata", {})
        if name in metadata:
            return metadata[name]
        
        try:
            return super().__getitem__(name)
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
    
    def __setattr__(self, name: str, value: Any):
        """Support dot setting for metadata fields"""
        internal_attrs = {"task", "current_step", "max_steps", "trajectory", 
                         "_final_result", "_memory_window", "metadata",
                         "_mutation_log"}
        
        property_map = {
            "final_result": "_final_result",
            "memory_window": "_memory_window",
        }
        
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        elif name in property_map:
            self[property_map[name]] = value
        elif name in internal_attrs:
            if name in self.keys():
                self[name] = value
            else:
                object.__setattr__(self, name, value)
        elif name in self.keys():
            self[name] = value
        else:
            if "metadata" not in self.keys():
                OrderedDict.__setitem__(self, "metadata", {})
            self["metadata"][name] = value
    
    def add_entry(
        self,
        role: str,
        content: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TrajectoryEntry:
        """
        Add trajectory entry
        
        Args:
            role: Role (user/assistant/action/observation)
            content: Content
            metadata: Optional metadata
            
        Returns:
            Created trajectory entry
        """
        step = self.get("current_step", 0)
        entry = TrajectoryEntry(
            role=role,
            content=content,
            step=step,
            metadata=metadata
        )
        
        trajectory = self.get("trajectory", [])
        trajectory.append(entry)
        
        window = self.memory_window
        if len(trajectory) > window:
            trajectory = trajectory[-window:]
        
        self["trajectory"] = trajectory
        
        return entry
    
    def get_history(
        self,
        roles: Optional[List[str]] = None,
        window: Optional[int] = None
    ) -> List[TrajectoryEntry]:
        """
        Get history trajectory (supports role filtering)
        
        Args:
            roles: Role list to filter, None means all roles
            window: Window size, default uses memory_window
            
        Returns:
            Filtered trajectory entry list
        """
        window = window or self.memory_window
        trajectory = self.get("trajectory", [])
        
        if not trajectory:
            return []
        
        entries = trajectory[-window:]
        
        if roles:
            entries = [e for e in entries if e.role in roles]
        
        return entries
    
    def get_trajectory_for_llm(self, window: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get trajectory format suitable for LLM
        
        Role conversion rules:
        - user -> {"role": "user", "content": ...}
        - assistant -> {"role": "assistant", "content": ...}
        - action -> {"role": "user", "content": f"Action: {content}"}
        - observation -> {"role": "user", "content": f"Observation: {content}"}
        
        Args:
            window: Window size
            
        Returns:
            Message list suitable for sending to LLM
        """
        entries = self.get_history(window=window)
        
        messages = []
        for entry in entries:
            if entry.role == "user":
                messages.append({"role": "user", "content": entry.content})
            elif entry.role == "assistant":
                messages.append({"role": "assistant", "content": entry.content})
            elif entry.role == "action":
                action_str = json.dumps(entry.content, ensure_ascii=False) if isinstance(entry.content, dict) else str(entry.content)
                messages.append({"role": "user", "content": f"Action: {action_str}"})
            elif entry.role == "observation":
                messages.append({"role": "user", "content": f"Observation: {entry.content}"})
        
        return messages
    
    def to_json(self, indent: int = 2) -> str:
        """
        Serialize AgentContext to JSON string
        
        Args:
            indent: JSON indent spaces
            
        Returns:
            JSON format string
        """
        reserved_keys = {"_mutation_log", "trajectory", "task", "current_step",
                        "max_steps", "_final_result", "_memory_window",
                        "metadata", "_exported_at"}
        
        state = {
            "task": self.get("task"),
            "current_step": self.get("current_step"),
            "max_steps": self.get("max_steps"),
            "trajectory": [entry.to_dict() for entry in self.get("trajectory", [])],
            "metadata": self.get("metadata", {}),
            "_final_result": self.get("_final_result"),
            "_memory_window": self.get("_memory_window", 5),
            "_mutation_log": [log.to_dict() for log in self.get("_mutation_log", [])],
            "_exported_at": datetime.now().isoformat()
        }
        
        for key in self.keys():
            if key not in reserved_keys:
                state[key] = self.get(key)
        
        return json.dumps(state, ensure_ascii=False, indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AgentContext':
        """Restore AgentContext from JSON string"""
        state = json.loads(json_str)
        
        reserved_keys = {"_mutation_log", "trajectory", "task", "current_step",
                        "max_steps", "_final_result", "_memory_window",
                        "metadata", "_exported_at"}
        
        context = cls.__new__(cls)
        OrderedDict.__init__(context)
        
        OrderedDict.__setitem__(context, "_mutation_log", [
            MutationLog.from_dict(log) 
            for log in state.get("_mutation_log", [])
        ])
        OrderedDict.__setitem__(context, "trajectory", [
            TrajectoryEntry.from_dict(entry)
            for entry in state.get("trajectory", [])
        ])
        
        OrderedDict.__setitem__(context, "task", state.get("task", ""))
        OrderedDict.__setitem__(context, "current_step", state.get("current_step", 0))
        OrderedDict.__setitem__(context, "max_steps", state.get("max_steps", 10))
        OrderedDict.__setitem__(context, "_final_result", state.get("_final_result"))
        OrderedDict.__setitem__(context, "_memory_window", state.get("_memory_window", 5))
        OrderedDict.__setitem__(context, "metadata", state.get("metadata", {}))
        
        for key, value in state.items():
            if key not in reserved_keys:
                OrderedDict.__setitem__(context, key, value)
        
        return context
    
    def get_mutations_since(self, step: int) -> List[MutationLog]:
        """Get all state changes after specified step"""
        return [log for log in self.get("_mutation_log", []) if log.step > step]
    
    def create_snapshot(self) -> Dict[str, Any]:
        """Create snapshot of current state (for Inspector)"""
        return {
            "context": json.loads(self.to_json()),
            "mutation_count": len(self.get("_mutation_log", [])),
            "step": self.get("current_step", 0),
            "trajectory_count": len(self.get("trajectory", [])),
            "history_count": len(self.get("trajectory", [])),
            "plan": self.get("plan", []),
            "plan_cursor": self.get("plan_cursor", 0),
            "plan_status": self.get("plan_status", "idle")
        }
    
    def __repr__(self) -> str:
        step = self.get("current_step", 0)
        task = self.get("task", "")
        meta_count = len(self.get("metadata", {}))
        mutation_count = len(self.get("_mutation_log", []))
        trajectory_count = len(self.get("trajectory", []))
        
        plan = self.get("plan", [])
        plan_cursor = self.get("plan_cursor", 0)
        plan_len = len(plan)
        
        plan_info = ""
        if plan_len > 0:
            plan_info = f" plan {plan_cursor}/{plan_len}"
        
        return (f"AgentContext(task='{task[:30]}...' "
                f"step={step}{plan_info}, "
                f"trajectory={trajectory_count}, "
                f"metadata={meta_count} fields)")
    
    def __str__(self) -> str:
        return self.__repr__()
