"""Tool abstraction and decorator for QitOS kernel."""

from __future__ import annotations

import inspect
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, cast, get_type_hints


@dataclass
class ToolPermission:
    filesystem_read: bool = False
    filesystem_write: bool = False
    network: bool = False
    command: bool = False


@dataclass(frozen=True)
class ToolPermissionSpec:
    """Serializable snapshot of a tool's permission and capability profile."""

    name: str
    description: str = ""
    permissions: ToolPermission = field(default_factory=ToolPermission)
    needs_approval: bool = False
    read_only: bool = False
    concurrency_safe: Optional[bool] = None
    required_ops: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permissions": asdict(self.permissions),
            "needs_approval": self.needs_approval,
            "read_only": self.read_only,
            "concurrency_safe": self.concurrency_safe,
            "required_ops": list(self.required_ops),
        }


@dataclass
class ToolValidationResult:
    valid: bool = True
    message: str = ""
    code: str = ""
    suggested_args: Optional[Dict[str, Any]] = None

    @classmethod
    def ok(cls) -> "ToolValidationResult":
        return cls(valid=True)

    @classmethod
    def fail(
        cls,
        message: str,
        *,
        code: str = "validation_failed",
        suggested_args: Optional[Dict[str, Any]] = None,
    ) -> "ToolValidationResult":
        return cls(
            valid=False, message=message, code=code, suggested_args=suggested_args
        )


_JSON_TYPES = frozenset(
    {"null", "boolean", "integer", "number", "string", "array", "object"}
)
_SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
        "oneOf",
        "enum",
        "nullable",
        # Annotation-only keywords do not change the accepted instance set.
        "title",
        "description",
        "default",
        "examples",
        "$comment",
        "deprecated",
        "readOnly",
        "writeOnly",
    }
)


def _matches_json_type(value: Any, declared: str) -> bool:
    if declared == "null":
        return value is None
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "string":
        return isinstance(value, str)
    if declared == "array":
        return isinstance(value, list)
    if declared == "object":
        return isinstance(value, dict)
    return False


def _schema_contract_failure(path: str, message: str) -> ToolValidationResult:
    location = path or "$"
    return ToolValidationResult.fail(
        f"Tool schema contract violation at '{location}': {message}",
        code="schema_contract_violation",
    )


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return bool(left == right)


def _validate_schema_contract(
    schema: Any,
    *,
    path: str,
    top_level: bool = False,
) -> ToolValidationResult:
    if not isinstance(schema, dict):
        return _schema_contract_failure(path, "schema node must be an object")
    unknown = sorted(str(key) for key in schema if key not in _SCHEMA_KEYWORDS)
    if unknown:
        return _schema_contract_failure(
            path, f"unsupported keyword '{unknown[0]}'"
        )

    declared = schema.get("type")
    if isinstance(declared, str):
        declared_types = [declared]
    elif isinstance(declared, list) and declared:
        if any(not isinstance(item, str) for item in declared):
            return _schema_contract_failure(path, "type array must contain strings")
        declared_types = list(declared)
    elif declared is None:
        declared_types = []
    else:
        return _schema_contract_failure(path, "type must be a string or non-empty array")
    unknown_types = sorted(set(declared_types) - _JSON_TYPES)
    if unknown_types:
        return _schema_contract_failure(
            path, f"unsupported JSON type '{unknown_types[0]}'"
        )
    if len(declared_types) != len(set(declared_types)):
        return _schema_contract_failure(path, "type array must not contain duplicates")
    if top_level and "object" not in declared_types:
        return _schema_contract_failure(path, "top-level type must include object")

    nullable = schema.get("nullable", False)
    if not isinstance(nullable, bool):
        return _schema_contract_failure(path, "nullable must be boolean")
    enum = schema.get("enum")
    if "enum" in schema and (not isinstance(enum, list) or not enum):
        return _schema_contract_failure(path, "enum must be a non-empty array")
    if isinstance(enum, list) and any(not _is_json_value(item) for item in enum):
        return _schema_contract_failure(path, "enum values must be finite JSON values")

    properties = schema.get("properties")
    if "properties" in schema:
        if not isinstance(properties, dict):
            return _schema_contract_failure(path, "properties must be an object")
        if declared_types and "object" not in declared_types:
            return _schema_contract_failure(path, "properties requires object type")
        for key, child_schema in properties.items():
            if not isinstance(key, str):
                return _schema_contract_failure(path, "property names must be strings")
            child = f"{path}.properties.{key}" if path else f"properties.{key}"
            result = _validate_schema_contract(child_schema, path=child)
            if not result.valid:
                return result

    required = schema.get("required")
    if "required" in schema:
        if not isinstance(required, list):
            return _schema_contract_failure(path, "required must be an array")
        if any(not isinstance(key, str) for key in required):
            return _schema_contract_failure(path, "required must contain strings")
        if len(required) != len(set(required)):
            return _schema_contract_failure(path, "required must not contain duplicates")
        if not isinstance(properties, dict):
            return _schema_contract_failure(path, "required needs declared properties")
        missing = sorted(key for key in required if key not in properties)
        if missing:
            return _schema_contract_failure(
                path, f"required property '{missing[0]}' is not declared"
            )

    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, (bool, dict)):
        return _schema_contract_failure(
            path, "additionalProperties must be boolean or a schema object"
        )
    if isinstance(additional, dict):
        result = _validate_schema_contract(
            additional, path=f"{path}.additionalProperties"
        )
        if not result.valid:
            return result

    if "items" in schema:
        if "array" not in declared_types:
            return _schema_contract_failure(path, "items requires array type")
        result = _validate_schema_contract(schema["items"], path=f"{path}.items")
        if not result.valid:
            return result

    if "anyOf" in schema and "oneOf" in schema:
        return _schema_contract_failure(path, "anyOf and oneOf cannot both be declared")
    for keyword in ("anyOf", "oneOf"):
        if keyword not in schema:
            continue
        alternatives = schema[keyword]
        if not isinstance(alternatives, list) or not alternatives:
            return _schema_contract_failure(path, f"{keyword} must be a non-empty array")
        for index, alternative in enumerate(alternatives):
            result = _validate_schema_contract(
                alternative, path=f"{path}.{keyword}[{index}]"
            )
            if not result.valid:
                return result
    return ToolValidationResult.ok()


def _validate_schema_value(
    value: Any,
    schema: Dict[str, Any],
    *,
    path: str,
) -> ToolValidationResult:
    if value is None and schema.get("nullable") is True:
        return ToolValidationResult.ok()

    alternative_keyword = "anyOf" if "anyOf" in schema else "oneOf" if "oneOf" in schema else ""
    if alternative_keyword:
        alternatives = schema[alternative_keyword]
        matches = 0
        for alternative in alternatives:
            if _validate_schema_value(value, alternative, path=path).valid:
                matches += 1
        if not matches or (alternative_keyword == "oneOf" and matches != 1):
            return ToolValidationResult.fail(
                f"Argument '{path}' does not match the declared {alternative_keyword} variants",
                code="invalid_argument_type",
            )

    declared = schema.get("type")
    declared_types = declared if isinstance(declared, list) else [declared]
    normalized_types = [str(item) for item in declared_types if item is not None]
    if normalized_types and not any(
        _matches_json_type(value, item) for item in normalized_types
    ):
        expected = "|".join(normalized_types)
        return ToolValidationResult.fail(
            f"Argument '{path}' must have JSON type {expected}",
            code="invalid_argument_type",
        )

    if "enum" in schema and not any(
        _json_equal(value, candidate) for candidate in schema["enum"]
    ):
        return ToolValidationResult.fail(
            f"Argument '{path}' is not one of the declared enum values",
            code="invalid_argument_value",
        )

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if isinstance(key, str) and key not in value:
                child = f"{path}.{key}" if path else key
                return ToolValidationResult.fail(
                    f"Missing required argument '{child}'",
                    code="missing_required_argument",
                )
        if schema.get("additionalProperties") is False:
            extra = sorted(str(key) for key in value if key not in properties)
            if extra:
                return ToolValidationResult.fail(
                    f"Unexpected argument '{extra[0]}'",
                    code="unexpected_argument",
                )
        for key, item in value.items():
            item_schema = properties.get(key)
            if item_schema is None and isinstance(schema.get("additionalProperties"), dict):
                item_schema = schema["additionalProperties"]
            if item_schema is None:
                continue
            child = f"{path}.{key}" if path else str(key)
            result = _validate_schema_value(item, item_schema, path=child)
            if not result.valid:
                return result

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            result = _validate_schema_value(
                item,
                schema["items"],
                path=f"{path}[{index}]",
            )
            if not result.valid:
                return result
    return ToolValidationResult.ok()


def validate_tool_arguments(
    args: Any,
    schema: Optional[Dict[str, Any]],
) -> ToolValidationResult:
    """Apply the non-bypassable structural JSON-schema subset for tool calls.

    This gate validates object shape, required keys, declared primitive and
    container types, nested properties/items, and ``additionalProperties``.
    Semantic problems discovered by a running tool belong in ``ToolResult``.
    """
    if not isinstance(args, dict):
        return ToolValidationResult.fail(
            "Tool arguments must be a JSON object",
            code="invalid_arguments_shape",
        )
    effective_schema = schema if schema is not None else {"type": "object"}
    if not isinstance(effective_schema, dict):
        return ToolValidationResult.fail(
            "Tool input schema must be an object",
            code="schema_contract_violation",
        )
    contract = _validate_schema_contract(effective_schema, path="$", top_level=True)
    if not contract.valid:
        return contract
    return _validate_schema_value(args, effective_schema, path="")


@dataclass
class ToolPermissionRule:
    effect: str  # allow | deny | ask
    tool_name: str = ""
    tool_family: str = ""
    scope: str = ""
    message: str = ""

    def matches(self, tool_name: str, scope: str = "") -> bool:
        normalized_tool = str(tool_name or "")
        normalized_scope = str(scope or "")
        if self.tool_name and self.tool_name != normalized_tool:
            return False
        if self.tool_family and not (
            normalized_tool == self.tool_family
            or normalized_tool.startswith(f"{self.tool_family}.")
        ):
            return False
        if self.scope and self.scope != normalized_scope:
            return False
        return bool(self.tool_name or self.tool_family or self.scope)


@dataclass
class ToolPermissionDecision:
    decision: str  # allow | deny | ask
    message: str = ""
    scope: str = ""
    matched_rule: Optional[ToolPermissionRule] = None
    updated_args: Optional[Dict[str, Any]] = None

    @classmethod
    def allow(
        cls, *, scope: str = "", updated_args: Optional[Dict[str, Any]] = None
    ) -> "ToolPermissionDecision":
        return cls(decision="allow", scope=scope, updated_args=updated_args)

    @classmethod
    def deny(
        cls,
        message: str,
        *,
        scope: str = "",
        matched_rule: Optional[ToolPermissionRule] = None,
    ) -> "ToolPermissionDecision":
        return cls(
            decision="deny", message=message, scope=scope, matched_rule=matched_rule
        )

    @classmethod
    def ask(
        cls,
        message: str,
        *,
        scope: str = "",
        matched_rule: Optional[ToolPermissionRule] = None,
        updated_args: Optional[Dict[str, Any]] = None,
    ) -> "ToolPermissionDecision":
        return cls(
            decision="ask",
            message=message,
            scope=scope,
            matched_rule=matched_rule,
            updated_args=updated_args,
        )


@dataclass
class ToolPermissionContext:
    allow_rules: List[ToolPermissionRule] = field(default_factory=list)
    deny_rules: List[ToolPermissionRule] = field(default_factory=list)
    ask_rules: List[ToolPermissionRule] = field(default_factory=list)
    default_decision: str = "allow"

    def evaluate(self, tool_name: str, scope: str = "") -> ToolPermissionDecision:
        for rule in self.deny_rules:
            if rule.matches(tool_name, scope):
                return ToolPermissionDecision.deny(
                    rule.message or f"Tool '{tool_name}' is denied.",
                    scope=scope,
                    matched_rule=rule,
                )
        for rule in self.ask_rules:
            if rule.matches(tool_name, scope):
                return ToolPermissionDecision.ask(
                    rule.message or f"Tool '{tool_name}' requires user confirmation.",
                    scope=scope,
                    matched_rule=rule,
                )
        for rule in self.allow_rules:
            if rule.matches(tool_name, scope):
                return ToolPermissionDecision.allow(scope=scope)
        if self.default_decision == "deny":
            return ToolPermissionDecision.deny(
                f"Tool '{tool_name}' is denied by the default permission policy.",
                scope=scope,
            )
        if self.default_decision == "ask":
            return ToolPermissionDecision.ask(
                f"Tool '{tool_name}' requires confirmation by the default permission policy.",
                scope=scope,
            )
        return ToolPermissionDecision.allow(scope=scope)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ToolPermissionContext":
        def _rules(items: Any) -> List[ToolPermissionRule]:
            rules: List[ToolPermissionRule] = []
            for item in list(items or []):
                if isinstance(item, ToolPermissionRule):
                    rules.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                rules.append(
                    ToolPermissionRule(
                        effect=str(item.get("effect", "")),
                        tool_name=str(item.get("tool_name", "")),
                        tool_family=str(item.get("tool_family", "")),
                        scope=str(item.get("scope", "")),
                        message=str(item.get("message", "")),
                    )
                )
            return rules

        return cls(
            allow_rules=_rules(payload.get("allow_rules")),
            deny_rules=_rules(payload.get("deny_rules")),
            ask_rules=_rules(payload.get("ask_rules")),
            default_decision=str(payload.get("default_decision", "allow")),
        )


@dataclass
class RetryPolicy:
    """Per-tool retry configuration with exponential backoff and exception filtering.

    When attached to a tool via ``@function_tool(retry_policy=...)`` or
    ``ToolSpec.retry_policy``, the :class:`ActionExecutor` uses this policy
    instead of the bare ``max_retries`` integer.

    Attributes:
        max_attempts: Total attempts including the first call (e.g. 3 = 1 initial + 2 retries).
        backoff_factor: Base delay in seconds for exponential backoff.
        max_backoff: Maximum delay cap in seconds.
        jitter: If True, add random jitter to backoff delay.
        retryable_exceptions: Tuple of exception types that trigger a retry.
            Other exceptions propagate immediately.
    """

    max_attempts: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 60.0
    jitter: bool = True
    retryable_exceptions: tuple = (Exception,)

    def __post_init__(self):
        for exc_type in self.retryable_exceptions:
            if not (isinstance(exc_type, type) and issubclass(exc_type, BaseException)):
                raise TypeError(
                    f"retryable_exceptions must contain exception types, got {exc_type!r}"
                )


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    timeout_s: Optional[float] = None
    max_retries: int = 0
    retry_policy: Optional[RetryPolicy] = None
    on_failure: Optional[Callable] = None
    permissions: ToolPermission = field(default_factory=ToolPermission)
    required_ops: List[str] = field(default_factory=list)
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    read_only: bool = False
    concurrency_safe: Optional[bool] = None
    needs_approval: bool = False
    requires_user_interaction: bool = False
    supports_background: bool = False
    result_max_chars: Optional[int] = None
    produces_artifact: bool = False
    rule_scope_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None
    prompt: str = ""


@dataclass
class ToolMeta:
    name: Optional[str] = None
    description: Optional[str] = None
    prompt: str = ""
    timeout_s: Optional[float] = None
    max_retries: int = 0
    retry_policy: Optional[RetryPolicy] = None
    on_failure: Optional[Callable] = None
    permissions: ToolPermission = field(default_factory=ToolPermission)
    required_ops: List[str] = field(default_factory=list)
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    read_only: bool = False
    concurrency_safe: Optional[bool] = None
    needs_approval: bool = False
    requires_user_interaction: bool = False
    supports_background: bool = False
    result_max_chars: Optional[int] = None
    produces_artifact: bool = False
    rule_scope_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None


class BaseTool:
    """Base abstraction for callable tools."""

    def __init__(self, spec: ToolSpec):
        # ``ToolSpec.description`` is an authored part of the model-facing
        # contract.  A method docstring is only a fallback for callers that did
        # not provide one; silently replacing an explicit description can turn
        # a rich ACI into the inherited generic ``BaseTool.execute`` text.
        explicit_description = str(spec.description or "").strip()
        if explicit_description:
            spec.description = inspect.cleandoc(explicit_description)
        else:
            description = (
                inspect.getdoc(self.execute)
                or inspect.getdoc(self.run)
                or inspect.getdoc(self.__class__)
            )
            if description:
                spec.description = inspect.cleandoc(description)
        if spec.input_schema is None:
            spec.input_schema = {
                "type": "object",
                "properties": dict(spec.parameters),
                "required": list(spec.required),
            }
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    def _coerce_run_kwargs(
        self, args: tuple[Any, ...], kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not args:
            return dict(kwargs)
        param_names = list(self.spec.parameters.keys())
        if len(args) > len(param_names):
            raise TypeError(
                f"{self.__class__.__name__}.run() received too many positional arguments"
            )
        merged = dict(kwargs)
        for name, value in zip(param_names, args):
            if name in merged:
                raise TypeError(
                    f"{self.__class__.__name__}.run() got multiple values for argument '{name}'"
                )
            merged[name] = value
        return merged

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Compatibility wrapper that routes legacy run calls through `execute(...)`."""
        runtime_context = kwargs.pop("runtime_context", None)
        coerced = self._coerce_run_kwargs(args, kwargs)
        return self.execute(coerced, runtime_context=runtime_context)

    def call(
        self, args: Dict[str, Any], runtime_context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Normalized call path for tool execution."""
        return self.execute(args, runtime_context=runtime_context)

    def validate_input(
        self,
        args: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> ToolValidationResult:
        _ = args
        _ = runtime_context
        return ToolValidationResult.ok()

    def validate_structure(self, args: Any) -> ToolValidationResult:
        """Validate the declared JSON shape before any tool code executes."""
        return validate_tool_arguments(args, self.spec.input_schema)

    def check_permissions(
        self,
        args: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> ToolPermissionDecision:
        runtime_context = runtime_context or {}
        context = runtime_context.get("permission_context")
        if isinstance(context, dict):
            context = ToolPermissionContext.from_dict(context)
        if not isinstance(context, ToolPermissionContext):
            return ToolPermissionDecision.allow(scope=self.build_rule_scope(args))
        return context.evaluate(self.name, self.build_rule_scope(args))

    def build_rule_scope(self, args: Dict[str, Any]) -> str:
        builder = getattr(self.spec, "rule_scope_builder", None)
        if callable(builder):
            value = builder(dict(args))
            return str(value or "")
        return ""

    def execute(
        self, args: Dict[str, Any], runtime_context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute tool with optional runtime context."""
        legacy_run = type(self).run
        if legacy_run is not BaseTool.run:
            call_kwargs = dict(args)
            run_sig = inspect.signature(legacy_run)
            if "runtime_context" in run_sig.parameters:
                call_kwargs["runtime_context"] = runtime_context
            return legacy_run(self, **call_kwargs)
        raise NotImplementedError

    def __call__(self, **kwargs: Any) -> Any:
        return self.run(**kwargs)


class FunctionTool(BaseTool):
    """Tool wrapper around callable functions or bound methods."""

    def __init__(self, func: Callable[..., Any], meta: Optional[ToolMeta] = None):
        self.func: Callable[..., Any]
        self.meta: ToolMeta
        # If func is already a FunctionTool (e.g. from __get__ binding),
        # unwrap it to get the underlying callable
        if isinstance(func, FunctionTool):
            self.func = func.func
            self.meta = meta or func.meta
            spec = func.spec
            super().__init__(spec)
            return
        self.func = func
        self.meta = meta or get_tool_meta(func) or ToolMeta()
        spec = build_tool_spec(func, self.meta)
        super().__init__(spec)
        # Match ``@function_tool``: explicit metadata wins, with the callable
        # docstring used only as a fallback.
        description = self.meta.description or inspect.getdoc(func)
        if description:
            self.spec.description = inspect.cleandoc(description)

    def __get__(self, obj, objtype=None):
        """Descriptor protocol: bind the tool to an instance when accessed as a method.

        This allows ``@function_tool`` to work on class methods the same way
        ``@tool`` does — the underlying function receives ``self`` automatically.
        """
        if obj is None:
            return self
        # Create a bound copy that prepends obj (self) to the function call
        bound = FunctionTool.__new__(FunctionTool)
        bound.func = self.func.__get__(obj, objtype)
        bound.meta = self.meta
        bound.spec = self.spec
        return bound

    def run(self, **kwargs: Any) -> Any:
        return self.func(**kwargs)

    def call(
        self, args: Dict[str, Any], runtime_context: Optional[Dict[str, Any]] = None
    ) -> Any:
        return self.execute(args, runtime_context=runtime_context)

    def execute(
        self, args: Dict[str, Any], runtime_context: Optional[Dict[str, Any]] = None
    ) -> Any:
        runtime_context = runtime_context or {}
        env = runtime_context.get("env")
        ops = runtime_context.get("ops", {})
        sig = inspect.signature(self.func)
        call_kwargs = dict(args)
        if "runtime_context" in sig.parameters:
            call_kwargs["runtime_context"] = runtime_context
        if "env" in sig.parameters:
            call_kwargs["env"] = env
        if "ops" in sig.parameters:
            call_kwargs["ops"] = ops
        if "file_ops" in sig.parameters and "file" in ops:
            call_kwargs["file_ops"] = ops["file"]
        if "process_ops" in sig.parameters and "process" in ops:
            call_kwargs["process_ops"] = ops["process"]
        return self.func(**call_kwargs)


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    prompt: str = "",
    timeout_s: Optional[float] = None,
    max_retries: int = 0,
    retry_policy: Optional[RetryPolicy] = None,
    on_failure: Optional[Callable] = None,
    permissions: Optional[ToolPermission] = None,
    required_ops: Optional[List[str]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    read_only: bool = False,
    concurrency_safe: Optional[bool] = None,
    needs_approval: bool = False,
    requires_user_interaction: bool = False,
    supports_background: bool = False,
    result_max_chars: Optional[int] = None,
    produces_artifact: bool = False,
    rule_scope_builder: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
):
    """Decorator that marks a callable as a QitOS tool without changing binding semantics."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        meta = ToolMeta(
            name=name,
            description=description,
            prompt=prompt,
            timeout_s=timeout_s,
            max_retries=max_retries,
            retry_policy=retry_policy,
            on_failure=on_failure,
            permissions=permissions or ToolPermission(),
            required_ops=list(required_ops or []),
            input_schema=input_schema,
            output_schema=output_schema,
            read_only=read_only,
            concurrency_safe=concurrency_safe,
            needs_approval=needs_approval,
            requires_user_interaction=requires_user_interaction,
            supports_background=supports_background,
            result_max_chars=result_max_chars,
            produces_artifact=produces_artifact,
            rule_scope_builder=rule_scope_builder,
        )
        setattr(func, "__qitos_tool_meta__", meta)
        setattr(func, "_is_tool", True)
        return func

    return decorator


def get_tool_meta(func: Callable[..., Any]) -> Optional[ToolMeta]:
    if hasattr(func, "__qitos_tool_meta__"):
        return getattr(func, "__qitos_tool_meta__")

    underlying = getattr(func, "__func__", None)
    if underlying is not None and hasattr(underlying, "__qitos_tool_meta__"):
        return getattr(underlying, "__qitos_tool_meta__")

    return None


def _parse_param_descriptions(docstring: str) -> Dict[str, str]:
    """Extract :param name: description pairs from a docstring.

    Supports both Sphinx style (``:param name: desc``) and Google style
    (``Args:\n    name: desc``) formats.
    """
    param_descs: Dict[str, str] = {}
    if not docstring:
        return param_descs
    # Sphinx / Epydoc style: :param name: description
    for m in re.finditer(
        r":param\s+(\w+)\s*:\s*(.*?)(?=\n\s*:param|\n\s*:type|\n\s*:return|\n\s*:raises|\Z)",
        docstring,
        re.DOTALL,
    ):
        name = m.group(1)
        desc = " ".join(m.group(2).split()).strip()
        if desc:
            param_descs[name] = desc
    # Google style: under "Args:" section, "    name: description"
    if not param_descs:
        args_match = re.search(
            r"(?:Args|Arguments|Parameters)\s*:\s*\n((?:\s+\w+.*\n?)+)",
            docstring,
        )
        if args_match:
            for line in args_match.group(1).splitlines():
                gm = re.match(r"\s+(\w+)\s*:\s*(.*)", line)
                if gm:
                    param_descs[gm.group(1)] = gm.group(2).strip()
    return param_descs


def _strip_param_docs(docstring: str) -> str:
    """Remove :param / :type / :return / :raises blocks from a docstring.

    These belong in parameter descriptions, not in the top-level tool
    description. A directive consumes its continuation lines (indented
    beyond the directive itself); once the text dedents again the rest of
    the docstring is kept.
    """
    if not docstring:
        return docstring
    lines = docstring.splitlines()
    cleaned: List[str] = []
    directive_indent: Optional[int] = None
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(
            (":param ", ":type ", ":return", ":raises ")
        ):
            directive_indent = len(line) - len(stripped)
            continue
        if directive_indent is not None and stripped:
            indent = len(line) - len(stripped)
            if indent > directive_indent:
                continue  # continuation line of the directive block
            directive_indent = None  # dedented: new section or prose
        cleaned.append(line)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return "\n".join(cleaned)


def build_tool_spec(func: Callable[..., Any], meta: ToolMeta) -> ToolSpec:
    sig = inspect.signature(func)
    target = getattr(func, "__func__", func)
    module = inspect.getmodule(target)
    globalns = getattr(module, "__dict__", {})
    try:
        resolved_hints = get_type_hints(
            target, globalns=globalns, localns=globalns, include_extras=True
        )
    except TypeError:
        try:
            resolved_hints = get_type_hints(target, globalns=globalns, localns=globalns)
        except Exception:
            resolved_hints = {}
    except Exception:
        resolved_hints = {}
    params = {}
    required = []

    raw_doc = inspect.getdoc(func) or ""
    param_descs = _parse_param_descriptions(raw_doc)

    for name, p in sig.parameters.items():
        if name in {
            "self",
            "cls",
            "runtime_context",
            "env",
            "ops",
            "file_ops",
            "process_ops",
        }:
            continue
        annotation = resolved_hints.get(name, p.annotation)
        params[name] = {
            "type": _type_to_json(annotation),
            "description": param_descs.get(name, ""),
        }
        if p.default is inspect.Parameter.empty:
            required.append(name)

    # Authored metadata wins; the docstring fallback has its :param blocks
    # stripped so per-parameter descriptions are not duplicated inline.
    desc = meta.description or _strip_param_docs(raw_doc) or ""
    tool_name = str(meta.name or getattr(func, "__name__", "tool") or "tool")

    return ToolSpec(
        name=cast(str, tool_name),
        description=inspect.cleandoc(desc) if desc else "",
        parameters=params,
        required=required,
        timeout_s=meta.timeout_s,
        max_retries=meta.max_retries,
        retry_policy=meta.retry_policy,
        on_failure=meta.on_failure,
        permissions=meta.permissions,
        required_ops=list(meta.required_ops),
        input_schema=meta.input_schema
        or {
            "type": "object",
            "properties": params,
            "required": required,
        },
        output_schema=meta.output_schema,
        read_only=meta.read_only,
        concurrency_safe=meta.concurrency_safe,
        needs_approval=meta.needs_approval,
        requires_user_interaction=meta.requires_user_interaction,
        supports_background=meta.supports_background,
        result_max_chars=meta.result_max_chars,
        produces_artifact=meta.produces_artifact,
        rule_scope_builder=meta.rule_scope_builder,
        prompt=meta.prompt,
    )


def _type_to_json(annotation: Any) -> str:
    if annotation in {inspect.Parameter.empty, inspect.Signature.empty}:
        return "string"

    if isinstance(annotation, str):
        normalized = annotation.strip().removeprefix("typing.")
        return {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "dict": "object",
            "Dict": "object",
            "list": "array",
            "List": "array",
            "None": "null",
            "NoneType": "null",
        }.get(normalized, "string")

    if annotation is Any:
        return "object"

    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
    }
    result = mapping.get(annotation)
    if result is not None:
        return result
    # Fallback to type_to_json_schema for complex types
    from .tool_schema import type_to_json_schema

    schema = type_to_json_schema(annotation)
    if isinstance(schema, dict) and "type" in schema and isinstance(schema["type"], str):
        return schema["type"]
    return "object"


__all__ = [
    "BaseTool",
    "FunctionTool",
    "RetryPolicy",
    "ToolMeta",
    "ToolPermission",
    "ToolPermissionContext",
    "ToolPermissionDecision",
    "ToolPermissionRule",
    "ToolSpec",
    "ToolValidationResult",
    "build_tool_spec",
    "get_tool_meta",
    "tool",
    "validate_tool_arguments",
]
