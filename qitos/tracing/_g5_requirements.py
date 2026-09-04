"""Integration-owned requirement authority; producers cannot extend this table.

Qualification pins are populated only after controlled consumer execution on a
committed fixing tree. A missing pin deliberately prevents readiness.
"""

SOURCE_HEADS = {
    "A": "f670e551f0bd5d88501182c2d24a5037fa0aebb9",
    "B": "c834ce76b939e86b33019719d5b212b1c7a38bdd",
    "C": "a1958fe620f9a80017d80aca702711991b80c8e6",
}
REPLAY_HEADS = {
    "A": "96f504b0f018584bf46eb065ba1029f98cce8b70", "B": "d278c44dd414690ccd5eee988bcc5c601c090e84", "C": "6b08da3188317810a4fb17b2aaa5553d062c84c7",
}

# requirement -> (owning writer, controlled qualification node)
REQUIREMENTS = {
    "A": {
        "public_composition": ("qitos.config.builder.AgentComposition", "tests/test_g5_session_public.py::test_default_sqlite_location_is_derived_and_unwritable_location_fails_before_model"),
        "session_default": ("qitos.engine.session_runtime.Session", "tests/test_g5_audit_regressions.py::test_g5_a2_default_durable_store_is_cross_process"),
        "cli_programmatic_equivalence": ("qitos.config.builder.AgentComposition", "tests/test_g5_audit_regressions.py::test_g5_a1_cli_fork_preserves_source_head"),
        "cleanup_ownership": ("qitos.config.builder.AgentComposition", "tests/test_s4_lane_a_public_authoring.py::test_context_manager_closes_owned_resources_after_body_failure"),
        "config_extension_slots": ("qitos.config.builder.AgentComposition", "tests/test_g5_composition_extensions.py::test_configured_context_memory_and_selector_reach_the_provider"),
    },
    "B": {
        "provider_transaction": ("qitos.models.provider.execute_provider_request", "tests/test_g5_audit_regressions.py::test_g5_b1_missing_capture_preserves_dispatch_fact"),
        "message_ordering": ("qitos.core.conversation.ExchangeLog", "tests/models/test_s4_provider_conformance.py::test_standalone_third_party_adapter_passes_reusable_conformance_runner"),
        "reasoning_continuation": ("qitos.models.provider.execute_provider_request", "tests/test_g5_audit_regressions.py::test_g5_b1_missing_capture_preserves_dispatch_fact"),
        "context_compaction_artifact": ("qitos.core.context", "tests/test_g5_composition_extensions.py::test_configured_compactor_runs_on_closed_exchange_omission"),
        "usage_loss_failure": ("qitos.models.provider.execute_provider_request", "tests/test_g5_audit_regressions.py::test_g5_b1_capture_failure_persists_budget_without_resend"),
    },
    "C": {
        "tool_result_aci": ("qitos.kit.toolset.env_coding", "tests/s4/lane_c/test_safe_execution.py::test_native_aci_is_small_env_only_and_permissions_are_split"),
        "sandbox_attestation": ("qitos.kit.env.sandbox.DockerSandboxBackend", "tests/test_g5_docker_owned.py::test_g5_real_docker_process_group_and_cleanup"),
        "effect_lifecycle": ("qitos.engine.tool_runtime.ReferenceEffectPolicy", "tests/test_g5_docker_owned.py::test_g5_unknown_backend_exit_keeps_ownership_and_cleanup_failure"),
        "mcp": ("qitos.mcp", "tests/mcp/test_g5_mcp_contract.py::test_mcp_large_result_is_retrievable_and_runtime_context_stays_local"),
        "work_graph_operations": ("qitos.engine.session_runtime.Session", "tests/engine/test_g5_real_work.py::test_real_child_session_completion_closes_durable_join"),
        "cleanup_unknown": ("qitos.kit.env.docker_env.DockerProcessControlCapability", "tests/test_g5_docker_owned.py::test_g5_unknown_backend_exit_keeps_ownership_and_cleanup_failure"),
    },
}

# (lane, requirement) -> exact committed qualification artifact identity.
# Intentionally empty until the installed G5 consumers and controlled nodes run.
QUALIFICATION_PINS: dict[tuple[str, str], dict[str, str]] = {}
