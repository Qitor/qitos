"""Resolve caller-owned extension factories at the sole composition boundary."""

from typing import Any, Mapping

from qitos.engine.runtime import LifecyclePolicy
from qitos.engine.states import ContextConfig

from .errors import CompositionError


def resolve_extensions(config: Any, registry: Mapping[str, Any]) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    def reject(field: str) -> None:
        raise CompositionError("configured extension is unavailable or unsupported", field=field)

    def resolve(name: Any, method: str, field: str) -> Any:
        if not isinstance(name, str) or name not in registry:
            reject(field)
        value = registry[name]
        if isinstance(value, type) or (callable(value) and not hasattr(value, method)):
            value = value()
        if not callable(getattr(value, method, None)):
            reject(field)
        return value

    context = dict(config.context)
    fields = set(ContextConfig.__dataclass_fields__)
    service_keys = {"contributors", "selector", "artifact_resolver", "continuation_resolver", "allow_codec_loss"}
    if set(context) - fields - service_keys:
        reject("context")
    engine_context = {key: value for key, value in context.items() if key in fields}
    services: dict[str, Any] = {}
    if "allow_codec_loss" in context:
        if not isinstance(context["allow_codec_loss"], bool):
            reject("context.allow_codec_loss")
        services["allow_codec_loss"] = context["allow_codec_loss"]
    contributors = context.get("contributors", ())
    if not isinstance(contributors, (list, tuple)):
        reject("context.contributors")
    services["context_contributors"] = tuple(
        resolve(name, "contribute", "context.contributors") for name in contributors
    )
    for key, field, method in (("selector", "context_selection_policy", "select"),
                               ("artifact_resolver", "artifact_resolver", "resolve"),
                               ("continuation_resolver", "continuation_resolver", "capture")):
        if key in context:
            services[field] = resolve(context[key], method, f"context.{key}")
    memory = dict(config.memory)
    if set(memory) - {"provider", "sources"}:
        reject("memory")
    names = memory.get("sources", (memory["provider"],) if "provider" in memory else ())
    if not isinstance(names, (list, tuple)):
        reject("memory.sources")
    services["memory_sources"] = tuple(resolve(name, "contribute", "memory.sources") for name in names)
    compaction = dict(config.compaction)
    if set(compaction) - {"provider"}:
        reject("compaction")
    if compaction:
        services["compaction_policy"] = resolve(compaction["provider"], "compact", "compaction.provider")
    lifecycle = dict(config.lifecycle)
    if set(lifecycle) - {"policy"}:
        reject("lifecycle")
    policy = lifecycle.get("policy", "cooperative")
    lifecycle_policy = LifecyclePolicy() if policy == "cooperative" else resolve(policy, "should_pause", "lifecycle.policy")
    if not callable(getattr(lifecycle_policy, "pause_safety", None)) or not hasattr(lifecycle_policy, "supports_pause"):
        reject("lifecycle.policy")
    for key, methods in (("artifact_resolver", ("resolve", "probe")),
                         ("continuation_resolver", ("capture", "resolve"))):
        if key in services and any(not callable(getattr(services[key], method, None)) for method in methods):
            reject(f"context.{key}")
    failures = dict(config.failure_policy)
    if set(failures) - {"tool"} or failures.get("tool", "continue") not in {"continue", "fail_closed"}:
        reject("failure_policy")
    options = dict(config.tool_options)
    if set(options) - {"native_tool_calls_required", "max_concurrency", "auto_approve"}:
        reject("tools.options")
    if (isinstance(options.get("max_concurrency", 4), bool)
            or not isinstance(options.get("max_concurrency", 4), int)
            or not 1 <= options.get("max_concurrency", 4) <= 64):
        reject("tools.options.max_concurrency")
    if any(key in options and not isinstance(options[key], bool)
           for key in ("native_tool_calls_required", "auto_approve")):
        reject("tools.options")
    return services, lifecycle_policy, engine_context
