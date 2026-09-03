"""Typed, secret-safe failures for declarative agent launch configuration."""

from __future__ import annotations

from typing import Any, Dict, Optional


class ConfigurationError(ValueError):
    """Base fail-closed configuration error with a stable public code."""

    code = "configuration_invalid"

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        remediation: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.field = field
        self.remediation = remediation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "field": self.field,
            "remediation": self.remediation,
        }


class ConfigSourceError(ConfigurationError):
    code = "config_source_invalid"


class ConfigSyntaxError(ConfigurationError):
    code = "config_syntax_invalid"


class ConfigSchemaError(ConfigurationError):
    code = "config_schema_invalid"


class UnknownConfigFieldError(ConfigSchemaError):
    code = "config_unknown_field"


class MissingEnvironmentVariableError(ConfigurationError):
    code = "environment_reference_missing"


class CredentialError(ConfigurationError):
    code = "credential_invalid"


class CredentialFileSecurityError(CredentialError):
    code = "credential_file_security_invalid"


class CredentialNotFoundError(CredentialError):
    code = "credential_reference_missing"


class CredentialResolutionError(CredentialError):
    code = "credential_resolution_failed"


class CompositionError(ConfigurationError):
    code = "agent_composition_failed"


class CompositionClosedError(CompositionError):
    code = "agent_composition_closed"


class CompositionCleanupError(CompositionError):
    code = "agent_composition_cleanup_failed"

    def __init__(self, message: str, *, failures: list[Dict[str, str]]) -> None:
        super().__init__(message, field="composition.resources")
        self.failures = tuple(dict(item) for item in failures)

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["failures"] = [dict(item) for item in self.failures]
        return payload


class UnsupportedProtocolError(CompositionError):
    code = "unsupported_protocol"


class ProtocolParserMismatchError(CompositionError):
    code = "protocol_parser_mismatch"


class ProviderCapabilityLossError(CompositionError):
    code = "provider_capability_loss"


class MalformedStructuredResponseError(CompositionError):
    code = "malformed_structured_response"


class ToolCallProjectionLossError(CompositionError):
    code = "tool_call_projection_loss"


class ContinuationUnavailableError(CompositionError):
    code = "continuation_unavailable"


class LossyFallbackNotAuthorizedError(CompositionError):
    code = "lossy_fallback_not_authorized"


class ToolUsePolicyViolationError(CompositionError):
    code = "tool_use_policy_violation"


class SandboxError(CompositionError):
    code = "sandbox_invalid"


class SandboxUnavailableError(SandboxError):
    code = "sandbox_unavailable"


class UnsafeHostConfigurationError(SandboxError):
    code = "unsafe_host_constraint_rejected"


class SandboxCleanupError(SandboxError):
    code = "sandbox_cleanup_failed"


class ConfigDigestMismatchError(CompositionError):
    code = "config_digest_mismatch"


class SourceBindingError(ConfigurationError):
    code = "source_binding_failed"


__all__ = [
    "CompositionError",
    "CompositionClosedError",
    "CompositionCleanupError",
    "ConfigDigestMismatchError",
    "ConfigSchemaError",
    "ConfigSourceError",
    "ConfigSyntaxError",
    "ConfigurationError",
    "CredentialError",
    "CredentialFileSecurityError",
    "CredentialNotFoundError",
    "CredentialResolutionError",
    "MissingEnvironmentVariableError",
    "ContinuationUnavailableError",
    "LossyFallbackNotAuthorizedError",
    "MalformedStructuredResponseError",
    "ProtocolParserMismatchError",
    "ProviderCapabilityLossError",
    "SandboxCleanupError",
    "SandboxError",
    "SandboxUnavailableError",
    "SourceBindingError",
    "ToolCallProjectionLossError",
    "ToolUsePolicyViolationError",
    "UnknownConfigFieldError",
    "UnsafeHostConfigurationError",
    "UnsupportedProtocolError",
]
