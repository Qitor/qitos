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


class SourceBindingError(ConfigurationError):
    code = "source_binding_failed"


__all__ = [
    "CompositionError",
    "ConfigSchemaError",
    "ConfigSourceError",
    "ConfigSyntaxError",
    "ConfigurationError",
    "CredentialError",
    "CredentialFileSecurityError",
    "CredentialNotFoundError",
    "CredentialResolutionError",
    "MissingEnvironmentVariableError",
    "SourceBindingError",
    "UnknownConfigFieldError",
]
