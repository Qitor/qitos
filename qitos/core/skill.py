"""
Skills System: Declarative tool system

Core feature: Writing tools is writing Python functions.
Leverages Python type hints and docstrings to auto-generate tool descriptions.

Features:
- Skill ABC base class: Implement tools via inheritance
- @skill decorator: Mark functions as Agent-available Skills (backward compatible)
- Auto-parse type annotations to generate Schema
- Auto-extract parameter descriptions from Docstrings
- Support sync/async tools
"""

import inspect
import re
from typing import Any, Callable, Dict, List, Optional, get_type_hints, get_origin, get_args
from dataclasses import dataclass
from abc import ABC, abstractmethod


class Skill(ABC):
    """
    Skill abstract base class
    
    Core: Define tools by inheriting from Skill class.
    Just implement run() method, get_spec() auto-generates Schema from signature and docstring.
    
    Example:
        class ReadFile(Skill):
            '''Read file content at specified path'''
            
            def __init__(self, root_dir: str = "/tmp", encoding: str = "utf-8"):
                super().__init__(name="read_file")
                self.root_dir = root_dir
                self.encoding = encoding
            
            def run(self, path: str) -> dict:
                '''
                Read file content
                
                Args:
                    path: Absolute file path
                    
                Returns:
                    Dict containing content or error
                '''
                full_path = os.path.join(self.root_dir, path)
                try:
                    with open(full_path, encoding=self.encoding) as f:
                        return {"status": "success", "content": f.read()}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
    """
    
    def __init__(self, name: str = None, **kwargs):
        """
        Initialize Skill
        
        Args:
            name: Skill name, defaults to class name
            **kwargs: Subclasses can define extra config params (e.g. root_dir, api_key, etc.)
        """
        self._name = name or self.__class__.__name__
        self._spec = None
        self._is_skill = True
    
    @property
    def name(self) -> str:
        """Get Skill name"""
        return self._name
    
    @property
    def domain(self) -> str:
        """Get Skill domain"""
        return getattr(self, '_domain', 'default')
    
    def run(self, **kwargs) -> Any:
        """
        Execute Skill logic
        
        Subclasses must implement this method.
        This method's signature and docstring will be parsed by get_spec() to generate Schema.
        
        Args:
            **kwargs: Tool parameters
            
        Returns:
            Execution result
        """
        pass
    
    def get_spec(self) -> Dict[str, Any]:
        """
        Get OpenAI-compatible Tool Specification
        
        Uses inspect to scan self.run signature and docstring,
        generates JSON Schema for LLM use.
        
        Returns:
            OpenAI-style Tool Specification
        """
        if self._spec is not None:
            return self._spec
        
        spec = self._parse_run_signature()
        self._spec = spec
        return spec
    
    def _parse_run_signature(self) -> Dict[str, Any]:
        """
        Parse run method signature and docstring
        
        Returns:
            OpenAI-style Tool Specification
        """
        sig = inspect.signature(self.run)
        params = sig.parameters
        
        parameters = {}
        required_params = []
        
        for param_name, param in params.items():
            if param_name in ["self", "cls"]:
                continue
            
            param_info = {
                "type": "any",
                "description": ""
            }
            
            if param.annotation is not inspect.Parameter.empty:
                param_info["type"] = self._get_type_name(param.annotation)
            
            param_info["description"] = self._extract_param_doc(
                self.run.__doc__ or "", param_name
            )
            
            parameters[param_name] = param_info
            
            if param.default is inspect.Parameter.empty:
                required_params.append(param_name)
        
        short_description = self._get_short_description(self.run.__doc__ or "")
        
        returns = {"type": "any", "description": ""}
        if sig.return_annotation is not inspect.Signature.empty:
            returns["type"] = self._get_type_name(sig.return_annotation)
            returns["description"] = self._extract_return_doc(
                self.run.__doc__ or ""
            )
        
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": short_description,
                "parameters": {
                    "type": "object",
                    "properties": parameters,
                    "required": required_params
                }
            }
        }
    
    def _get_type_name(self, annotation: Any) -> str:
        """
        Get string representation of type
        
        Args:
            annotation: Type annotation object
            
        Returns:
            String representation of type (e.g. "string", "integer", "array", etc.)
        """
        if annotation is inspect.Parameter.empty:
            return "any"
        
        if isinstance(annotation, str):
            return "string"
        
        origin = get_origin(annotation)
        
        if origin is None:
            type_map = {
                str: "string", int: "integer", float: "number",
                bool: "boolean", list: "array", dict: "object",
                Any: "any", type(None): "null"
            }
            
            if annotation in type_map:
                return type_map[annotation]
            
            try:
                return annotation.__name__
            except AttributeError:
                return "any"
        
        return self._get_generic_type_name(annotation, origin)
    
    def _get_generic_type_name(self, annotation: Any, origin: Any) -> str:
        """
        Handle generic type names
        
        Args:
            annotation: Type annotation object
            origin: Generic origin (e.g. list, dict)
            
        Returns:
            String representation of generic type
        """
        args = get_args(annotation)
        
        if origin is list:
            if args:
                item_type = self._get_type_name(args[0])
                return f"array[{item_type}]"
            return "array"
        
        if origin is dict:
            if len(args) >= 2:
                key_type = self._get_type_name(args[0])
                value_type = self._get_type_name(args[1])
                return f"object<{key_type}, {value_type}>"
            return "object"
        
        try:
            return origin.__name__
        except AttributeError:
            return "any"
    
    def _extract_param_doc(self, docstring: str, param_name: str) -> str:
        """
        Extract parameter description from docstring
        
        Supported formats:
        - :param param_name: description (Google/Sphinx style)
        - Args:
              param_name: description
        - param_name: description
        
        Args:
            docstring: Docstring
            param_name: Parameter name
            
        Returns:
            Parameter description
        """
        if not docstring:
            return ""
        
        # 1. Try matching :param param_name: description format (Sphinx/Google style)
        sphinx_pattern = rf':param\s+{param_name}\s*:\s*(.+?)(?=:param|:return|\n\s*\n|\Z)'
        match = re.search(sphinx_pattern, docstring, re.IGNORECASE | re.DOTALL)
        if match:
            desc = match.group(1).strip()
            desc = re.sub(r'\s+', ' ', desc)
            return desc
        
        # 2. Try matching Args: section format
        args_section_pattern = r'Args:\s*\n(.+?)(?=Returns?:|\n\s*\n|\Z)'
        args_section = re.search(args_section_pattern, docstring, re.IGNORECASE | re.DOTALL)
        if args_section:
            args_text = args_section.group(1)
            # Find parameter in Args section
            param_pattern = rf'^\s*{param_name}\s*[:：]\s*(.+?)(?=^\s*\w+\s*[:：]|\Z)'
            param_match = re.search(param_pattern, args_text, re.MULTILINE | re.DOTALL)
            if param_match:
                desc = param_match.group(1).strip()
                desc = re.sub(r'\s+', ' ', desc)
                return desc
        
        # 3. Try matching simple param_name: description format
        simple_patterns = [
            rf'{param_name}\s*[:：]\s*(.+?)(?:\n\s*\w|\Z)',
            rf'{param_name}\s*[-–]\s*(.+?)(?:\n\s*\w|\Z)',
            rf'\b{param_name}\b[:\s]+(.+?)(?:\n\s*\w|\Z)',
        ]
        
        for pattern in simple_patterns:
            match = re.search(pattern, docstring, re.IGNORECASE | re.DOTALL)
            if match:
                desc = match.group(1).strip()
                desc = re.sub(r'\s+', ' ', desc)
                return desc
        
        return ""
    
    def _extract_return_doc(self, docstring: str) -> str:
        """
        Extract return value description from docstring
        
        Supported formats:
        - :return: description (Sphinx style)
        - :returns: description
        - Returns: description
        
        Args:
            docstring: Docstring
            
        Returns:
            Return value description
        """
        if not docstring:
            return ""
        
        # 1. Try matching :return: or :returns: format (Sphinx style)
        sphinx_pattern = r':returns?:\s*(.+?)(?=:param|:raise|\n\s*\n|\Z)'
        match = re.search(sphinx_pattern, docstring, re.IGNORECASE | re.DOTALL)
        if match:
            desc = match.group(1).strip()
            desc = re.sub(r'\s+', ' ', desc)
            return desc
        
        # 2. Try matching Returns: section format
        returns_section_pattern = r'Returns?:\s*\n(.+?)(?=Raises?:|\n\s*\n|\Z)'
        returns_section = re.search(returns_section_pattern, docstring, re.IGNORECASE | re.DOTALL)
        if returns_section:
            desc = returns_section.group(1).strip()
            desc = re.sub(r'\s+', ' ', desc)
            return desc
        
        # 3. Try matching simple Returns: description format
        patterns = [
            r'Returns?\s*[:：]\s*(.+?)(?:\n\s*\w|\Z)',
            r'Return\s*[:：]\s*(.+?)(?:\n\s*\w|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, docstring, re.IGNORECASE | re.DOTALL)
            if match:
                desc = match.group(1).strip()
                desc = re.sub(r'\s+', ' ', desc)
                return desc
        
        return ""
    
    def _get_short_description(self, docstring: str) -> str:
        """
        Get short description (first non-empty line)
        
        Args:
            docstring: Docstring
            
        Returns:
            Short description
        """
        if not docstring:
            return ""
        
        for line in docstring.split('\n'):
            line = line.strip()
            if line:
                return line
        
        return ""
    
    @property
    def schema(self) -> 'ToolSchema':
        """Get ToolSchema compatible with old interface"""
        spec = self.get_spec()
        func_spec = spec.get("function", spec)
        
        params = func_spec.get("parameters", {})
        properties = params.get("properties", {})
        required = params.get("required", [])
        
        return ToolSchema(
            name=func_spec.get("name", self._name),
            description=func_spec.get("description", ""),
            parameters=properties,
            returns={"type": "any", "description": ""}
        )
    
    def __call__(self, **kwargs) -> Any:
        """
        Execute Skill
        
        Args:
            **kwargs: Tool parameters
            
        Returns:
            Execution result
        """
        return self.run(**kwargs)
    
    def __repr__(self) -> str:
        return f"Skill(name='{self._name}', domain='{self.domain}')"


class ToolSchema:
    """
    Tool parameter Schema (backward compatible interface)
    
    Internal use, auto-converted from Skill
    """
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Dict], returns: Dict[str, str]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.returns = returns
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": "object",
            "properties": {
                name: {
                    "type": param.get("type", "string"),
                    "description": param.get("description", "")
                }
                for name, param in self.parameters.items()
            },
            "required": list(self.parameters.keys()),
            "returns": self.returns
        }


class _FunctionSkill(Skill):
    """
    Convert regular function to Skill (internal use)
    """
    
    def __init__(self, func: Callable, domain: str = "default"):
        super().__init__(name=func.__name__)
        self._func = func
        self._domain = domain
        self._doc = func.__doc__ or ""
    
    def run(self, **kwargs) -> Any:
        return self._func(**kwargs)
    
    def __call__(self, **kwargs) -> Any:
        """Execute tool function with error handling"""
        try:
            return self.run(**kwargs)
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "tool": self._name
            }
    
    @property
    def domain(self) -> str:
        return self._domain
    
    def _parse_run_signature(self) -> Dict[str, Any]:
        """
        Parse original function signature (not run method signature)
        
        Returns:
            OpenAI-style Tool Specification
        """
        sig = inspect.signature(self._func)
        params = sig.parameters
        
        parameters = {}
        required_params = []
        
        for param_name, param in params.items():
            if param_name in ["self", "cls"]:
                continue
            
            param_info = {
                "type": "any",
                "description": ""
            }
            
            if param.annotation is not inspect.Parameter.empty:
                param_info["type"] = self._get_type_name(param.annotation)
            
            param_info["description"] = self._extract_param_doc(
                self._doc or "", param_name
            )
            
            parameters[param_name] = param_info
            
            if param.default is inspect.Parameter.empty:
                required_params.append(param_name)
        
        short_description = self._get_short_description(self._doc or "")
        
        returns = {"type": "any", "description": ""}
        if sig.return_annotation is not inspect.Signature.empty:
            returns["type"] = self._get_type_name(sig.return_annotation)
            returns["description"] = self._extract_return_doc(self._doc or "")
        
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": short_description,
                "parameters": {
                    "type": "object",
                    "properties": parameters,
                    "required": required_params
                }
            }
        }


def skill(domain: str = "default", name: Optional[str] = None):
    """
    Decorator: Mark a function as Agent-available Skill (backward compatible)
    
    Args:
        domain: Tool domain, used for categorization
        name: Tool name, defaults to function name
        
    Returns:
        Skill wrapper object
    
    Example:
        @skill(domain="file_io")
        def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
            '''
            Read file content at specified path.
            
            Args:
                path: Absolute file path
                encoding: File encoding, default utf-8
            Returns:
                Dict containing content or error
            '''
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Keep original callable to preserve binding semantics for instance methods.
        # ToolRegistry will wrap callables into Skill objects during registration.
        func._is_skill = True
        func._domain = domain
        func._name = name or func.__name__
        return func
    return decorator


class ToolRegistry:
    """
    Tool registry center
    
    Features:
    - Register and manage Skills
    - Auto-generate tool list
    - Support sync/async calls
    - Provide tool descriptions for LLM use
    
    Example:
        registry = ToolRegistry()
        registry.register(read_file)
        registry.register(write_file)
        
        # Get all available tools
        tools = registry.list_tools()
        
        # Call tool
        result = registry.call("read_file", path="/tmp/test.txt")
    """
    
    def __init__(self, skills: Optional[List[Callable]] = None):
        self._skills: Dict[str, Skill] = {}
        self._domains: Dict[str, List[str]] = {}
        
        if skills:
            for skill_func in skills:
                self.register(skill_func)
    
    def register(
        self, 
        func: Callable, 
        name: Optional[str] = None, 
        domain: Optional[str] = None
    ) -> 'ToolRegistry':
        """
        Register a tool function
        
        Args:
            func: Function or Skill object to register
            name: Custom tool name
            domain: Custom domain
            
        Returns:
            self, supports chaining
        """
        if isinstance(func, Skill):
            skill_obj = func
            if name:
                skill_obj._name = name
            if domain:
                if hasattr(skill_obj, '_domain'):
                    skill_obj._domain = domain
        else:
            skill_domain = domain or getattr(func, '_domain', 'default')
            skill_name = name or getattr(func, '_name', func.__name__)
            skill_obj = _FunctionSkill(func, skill_domain)
            skill_obj._name = skill_name
        
        self._skills[skill_obj.name] = skill_obj
        
        if hasattr(skill_obj, '_domain'):
            skill_domain = skill_obj._domain
        else:
            skill_domain = 'default'
        
        if skill_domain not in self._domains:
            self._domains[skill_domain] = []
        if skill_obj.name not in self._domains[skill_domain]:
            self._domains[skill_domain].append(skill_obj.name)
        
        return self
    
    def unregister(self, name: str) -> bool:
        """
        Unregister a tool
        
        Args:
            name: Tool name
            
        Returns:
            Whether unregistration succeeded
        """
        if name in self._skills:
            skill_obj = self._skills[name]
            if hasattr(skill_obj, '_domain'):
                skill_domain = skill_obj._domain
            else:
                skill_domain = 'default'
            
            if skill_domain in self._domains:
                if name in self._domains[skill_domain]:
                    self._domains[skill_domain].remove(name)
            
            del self._skills[name]
            return True
        return False
    
    def include(self, obj: Any, domain: Optional[str] = None) -> 'ToolRegistry':
        """
        Auto-register all @skill decorated methods from a Skill class instance.
        
        This method uses reflection to find all methods decorated with @skill
        on the given object and registers them individually.
        
        Args:
            obj: Skill class instance (e.g., EditorSkill(), FileSkill())
                  or any object with @skill decorated methods
            domain: Optional domain for all discovered skills
            
        Returns:
            self, supports chaining
            
        Example:
            editor = EditorSkill(workspace_root=".")
            registry.include(editor)
            # All @skill methods on EditorSkill are now registered
        """
        if not hasattr(obj, '__dict__'):
            return self
        
        skill_methods = []
        
        for attr_name in dir(obj):
            if attr_name.startswith('_'):
                continue
            
            attr = getattr(obj, attr_name)
            underlying = getattr(attr, "__func__", None)
            is_marked = (
                (hasattr(attr, '_is_skill') and attr._is_skill)
                or (underlying is not None and hasattr(underlying, "_is_skill") and underlying._is_skill)
            )
            if callable(attr) and is_marked:
                skill_methods.append(attr_name)
        
        if not skill_methods:
            return self
        
        for method_name in skill_methods:
            method = getattr(obj, method_name)
            method_domain = domain or getattr(method, '_domain', 'default')
            method_name_override = getattr(method, '_name', None)
            self.register(method, name=method_name_override, domain=method_domain)
        
        return self
    
    def get(self, name: str) -> Optional[Skill]:
        """
        Get tool by name
        
        Args:
            name: Tool name
            
        Returns:
            Skill object, or None if not exists
        """
        return self._skills.get(name)
    
    def list_tools(self, domain: Optional[str] = None) -> List[str]:
        """
        List all available tools
        
        Args:
            domain: Filter by domain
            
        Returns:
            Tool name list
        """
        if domain:
            return self._domains.get(domain, [])
        return list(self._skills.keys())
    
    def list_all(self) -> List[Skill]:
        """
        List all tool details
        
        Returns:
            Skill object list
        """
        return list(self._skills.values())
    
    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get Schema for specified tool (backward compatible interface)
        
        Args:
            name: Tool name
            
        Returns:
            Schema dict, or None if not exists
        """
        skill_obj = self.get(name)
        if skill_obj:
            return skill_obj.schema.to_dict()
        return None
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """
        Get all tool Schemas (for LLM use)
        
        Returns:
            Schema dict list
        """
        return [skill.get_spec() for skill in self._skills.values()]
    
    def get_schemas(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tool Schemas (for {{tool_schema}} placeholder replacement)
        
        Args:
            domain: Optional, filter by domain
            
        Returns:
            Formatted tool definition dict, containing tools key
        """
        if domain:
            tool_names = self._domains.get(domain, [])
            skills = [self._skills[name] for name in tool_names if name in self._skills]
        else:
            skills = list(self._skills.values())
        
        schemas = []
        for skill_obj in skills:
            spec = skill_obj.get_spec()
            schemas.append(spec)
        
        return {
            "tools": schemas,
            "count": len(schemas)
        }
    
    def get_tool_descriptions(self) -> str:
        """
        Generate tool description text (for LLM prompt use)
        
        Returns:
            Formatted tool descriptions
        """
        lines = []
        
        for name, skill_obj in sorted(self._skills.items()):
            spec = skill_obj.get_spec()
            func_spec = spec.get("function", spec)
            
            lines.append(f"## {name}")
            lines.append(f"Description: {func_spec.get('description', '')}")
            lines.append("Parameters:")
            
            params = func_spec.get("parameters", {}).get("properties", {})
            for param_name, param_info in params.items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                lines.append(f"  - {param_name} ({param_type}): {param_desc}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def call(self, name: str, **kwargs) -> Any:
        """
        Call specified tool
        
        Args:
            name: Tool name
            **kwargs: Tool parameters
            
        Returns:
            Tool execution result
        """
        skill_obj = self.get(name)
        if skill_obj is None:
            return {
                "status": "error",
                "message": f"Tool '{name}' not found",
                "available_tools": self.list_tools()
            }
        
        return skill_obj(**kwargs)
    
    def __contains__(self, name: str) -> bool:
        """Support `name in registry` syntax"""
        return name in self._skills
    
    def __getitem__(self, name: str) -> Skill:
        """Support `registry[name]` syntax"""
        return self._skills[name]
    
    def __iter__(self):
        """Support iteration over tool names"""
        return iter(self._skills)
    
    def __len__(self) -> int:
        """Return tool count"""
        return len(self._skills)
    
    def __repr__(self) -> str:
        return f"ToolRegistry(tools={len(self._skills)}, domains={len(self._domains)})"
    
    def __eq__(self, other) -> bool:
        """Compare two ToolRegistries for equality"""
        if not isinstance(other, ToolRegistry):
            return False
        return self._skills == other._skills and self._domains == other._domains


class AsyncToolRegistry(ToolRegistry):
    """
    Async tool registry center
    
    Supports async tool function registration and calls
    """
    
    async def call(self, name: str, **kwargs) -> Any:
        """
        Async call specified tool
        
        Args:
            name: Tool name
            **kwargs: Tool parameters
            
        Returns:
            Tool execution result
        """
        skill_obj = self.get(name)
        if skill_obj is None:
            return {
                "status": "error",
                "message": f"Tool '{name}' not found",
                "available_tools": self.list_tools()
            }
        
        func = skill_obj.run
        
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(**kwargs))
    
    def call_sync(self, name: str, **kwargs) -> Any:
        """
        Sync call (backward compatible interface)
        """
        skill_obj = self.get(name)
        if skill_obj:
            return skill_obj(**kwargs)
        return {
            "status": "error",
            "message": f"Tool '{name}' not found"
        }
