# Contributing to QitOS documentation

Start with the root working agreement and docs/AGENTS.md. Correct the existing
page before creating a parallel tutorial. Pair English and Chinese changes,
register complete examples in tutorial-contracts.json, and update docs.json.

Python fences are illustrative fragments unless the page binds a complete
executable example. Signatures use text fences. Configuration fragments are
labelled; full agent.yaml is parsed by load_agent_config. Never execute arbitrary
shell from prose. tests/test_docs_golden_paths.py runs only named offline lessons.

Run the checks in README.md, the tutorial tests, and git diff --check. Inspect
real Mintlify pages, not just file existence. Document tested source identity,
Python and tool versions, runtime boundaries and failures. Keep current state
above historical records; preserve historical evidence and raw-log digests.

Do not publish secrets, raw provider payloads or local paths. Remote branch
sync, default-branch promotion, package release and docs deployment are separate
operations requiring the applicable authorization.
