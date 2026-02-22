# `qitos.core.tool`

- 模块分组: `qitos.core`
- 源码: [qitos/core/tool.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `BaseTool`](#class-basetool)
- [Class: `FunctionTool`](#class-functiontool)
- [Class: `ToolMeta`](#class-toolmeta)
- [Class: `ToolPermission`](#class-toolpermission)
- [Class: `ToolSpec`](#class-toolspec)
- [Function: `build_tool_spec`](#function-build-tool-spec)
- [Function: `get_tool_meta`](#function-get-tool-meta)
- [Function: `tool`](#function-tool)

## Classes

<a id="class-basetool"></a>
???+ note "Class: `BaseTool(self, spec: 'ToolSpec')`"
    Base abstraction for callable tools.

<a id="class-functiontool"></a>
???+ note "Class: `FunctionTool(self, func: 'Callable[..., Any]', meta: 'Optional[ToolMeta]' = None)`"
    Tool wrapper around callable functions or bound methods.

<a id="class-toolmeta"></a>
???+ note "Class: `ToolMeta(self, name: 'Optional[str]' = None, description: 'Optional[str]' = None, timeout_s: 'Optional[float]' = None, max_retries: 'int' = 0, permissions: 'ToolPermission' = <factory>, required_ops: 'List[str]' = <factory>) -> None`"
    ToolMeta(name: 'Optional[str]' = None, description: 'Optional[str]' = None, timeout_s: 'Optional[float]' = None, max_retries: 'int' = 0, permissions: 'ToolPermission' = <factory>, required_ops: 'List[str]' = <factory>)

<a id="class-toolpermission"></a>
???+ note "Class: `ToolPermission(self, filesystem_read: 'bool' = False, filesystem_write: 'bool' = False, network: 'bool' = False, command: 'bool' = False) -> None`"
    ToolPermission(filesystem_read: 'bool' = False, filesystem_write: 'bool' = False, network: 'bool' = False, command: 'bool' = False)

<a id="class-toolspec"></a>
???+ note "Class: `ToolSpec(self, name: 'str', description: 'str', parameters: 'Dict[str, Dict[str, Any]]' = <factory>, required: 'List[str]' = <factory>, timeout_s: 'Optional[float]' = None, max_retries: 'int' = 0, permissions: 'ToolPermission' = <factory>, required_ops: 'List[str]' = <factory>) -> None`"
    ToolSpec(name: 'str', description: 'str', parameters: 'Dict[str, Dict[str, Any]]' = <factory>, required: 'List[str]' = <factory>, timeout_s: 'Optional[float]' = None, max_retries: 'int' = 0, permissions: 'ToolPermission' = <factory>, required_ops: 'List[str]' = <factory>)

## Functions

<a id="function-build-tool-spec"></a>
???+ note "Function: `build_tool_spec(func: 'Callable[..., Any]', meta: 'ToolMeta') -> 'ToolSpec'`"
    _No summary available._

<a id="function-get-tool-meta"></a>
???+ note "Function: `get_tool_meta(func: 'Callable[..., Any]') -> 'Optional[ToolMeta]'`"
    _No summary available._

<a id="function-tool"></a>
???+ note "Function: `tool(name: 'Optional[str]' = None, description: 'Optional[str]' = None, timeout_s: 'Optional[float]' = None, max_retries: 'int' = 0, permissions: 'Optional[ToolPermission]' = None, required_ops: 'Optional[List[str]]' = None)`"
    Decorator that marks a callable as a QitOS tool without changing binding semantics.

## Source Index

- [qitos/core/tool.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool.py)