# QitOS

<img src="assets/logo.png" alt="QitOS Logo" width="75%">

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.mintlify.app-0A66C2)](https://qitor.mintlify.app/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-WhitzardAgent%2FWhitzardOS-black)](https://github.com/WhitzardAgent/WhitzardOS)

QitOS is the torch-flavor framework for agent researchers.

Prototype methods, run benchmarks, and inspect long-horizon trajectories on one `AgentModule + Engine` kernel with built-in `qita` observability.

QitOS core is the small framework. Product-grade applications and showcase agents live in `qitos-zoo`, including planned apps such as `qitos-coder` and `qitos-cyber-agent`.

[Quickstart](https://qitor.mintlify.app/quickstart) · [Tutorial Track](https://qitor.mintlify.app/tutorials/index) · [Benchmarks](https://qitor.mintlify.app/benchmarks/overview) · [CLI Reference](https://qitor.mintlify.app/reference/cli) · [Changelog](CHANGELOG.md) · [Chinese README](README.zh.md)

## What you can build

Build multi-round tool Agents on one `AgentModule + Engine` kernel, with Session
pause, restore, fork and handoff. Configure budgets in YAML, select durable memory
and explicit compaction policies, and inspect or export canonical Trajectory with
qita. Extend tools, providers, context, stores, sinks and sandboxes. The framework
owns execution correctness; application strategy and model behavior remain with
the application and provider.

## What's New

- Agent Design Lab is in development: custom `agent_factory` composition, durable skill revisions, explicit memory deletion and corrected child workspace restoration support six professional teaching projects. See the [implementation ledger](docs/internal/plans/agent_design_lab_execution.md); the complete course/live matrix is not yet qualified.
- Python 3.10 model cleanup compatibility: every owned resource is attempted, with safe numeric cleanup diagnostics and primary exception priority preserved.
- R1 local integration and all five review repairs are complete: reasoning, accurate request/cleanup facts, handoff ownership and YAML budget/loss wiring; restoration retains original conversation facts.
- Memdir recall and closed-exchange compaction, canonical Read/Edit ToolResult, consistent Observation, strict snapshot paging and atomic export are available through the user workflow.
- Bilingual tutorials include complete runnable files, and API Reference binds to exact implementation source. See [migration guidance](docs/reference/g5-migration.mdx) for compatibility changes.

[Current R1 status and remote synchronization](docs/internal/plans/v5_r1_remote_sync.md)
is the sole status entry; the [V5 roadmap](docs/v5/README.md) retains subsequent scope.
R1 completion does not complete V5. Offline framework qualification does not imply
live-model qualification, a package release or a documentation deployment.

## Start developing

`pip install qitos` selects a published PyPI version, not an identity for unreleased R1.
Follow [Installation](docs/installation.mdx), then the
[credential-free Quickstart](docs/quickstart.mdx).
Real providers use [agent.yaml, CredentialRef and an explicit resolver](docs/reference/configuration.mdx).
Docker file tools fail closed when unavailable; they do not fall back to host execution.

## Learn and contribute

- [Eight learning units](docs/tutorials/index.mdx): custom Agents, parallel tools, Sessions, context/memory, sandbox/artifacts, multi-agent work, qita and third-party extensions.
- [Complete teaching files](examples/tutorials) and [example directory](examples/README.md).
- [Migration, limits and troubleshooting](docs/reference/g5-migration.mdx).
- [Contributing](docs/contributing/development.mdx) and [architecture](ARCHITECTURE.md).
- [CHANGELOG](CHANGELOG.md), [historical engineering progress](docs/progress.md) and [G5 evidence](docs/internal/plans/s4_g5_convergence_execution.md).

Advanced `AgentModule.run()` and historical trace compatibility remain supported.
