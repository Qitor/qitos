"""Third-party-shaped programmatic golden path; no repository-private imports."""

from qitos.config import build_agent_composition, load_agent_config


def run(config_path, resolver, task):
    config = load_agent_config(config_path)
    with build_agent_composition(
        config,
        credential_resolver=resolver,
    ) as composition:
        session = composition.session(task)
        return session.run()
