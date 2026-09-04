"""Validate configuration by default; --live explicitly opts into model requests."""
import argparse
from pathlib import Path

from notes import summarize_note
from qitos.config import LocalCredentialFileResolver, build_agent_composition, load_agent_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--credentials", type=Path, default=Path.home() / ".config/qitos/credentials.yaml")
    args = parser.parse_args()
    config = load_agent_config(Path(__file__).with_name("real_agent.yaml"))
    assert config.budgets.max_requests == 6
    if not args.live:
        print("configuration valid; no credentials read; no model request")
        return
    if config.model.base_url == "https://provider.example/v1":
        raise ValueError("Replace the reserved provider.example endpoint and example-model first")
    resolver = LocalCredentialFileResolver(args.credentials, repository_root=Path.cwd())
    with build_agent_composition(config, credential_resolver=resolver) as composition:
        composition.tool_registry.register(summarize_note)
        result = composition.session(
            "Call summarize_note for indices 0 and 1. Report both titles and word counts."
        ).run()
        print(composition.config.name, result.state.stop_reason, result.state.final_result)
        outputs = [a.output for record in result.records for a in record.action_results
                   if a.tool_name == "summarize_note" and a.status == "success"]
        assert {item["title"] for item in outputs} == {"Session", "Artifact"}, outputs


if __name__ == "__main__":
    main()
