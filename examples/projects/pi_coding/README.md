# Pi-like extensible coding

Status: in development, not course-qualified. The working source below is not a claim of a passed 3×3 live matrix. See the [execution ledger](../../../docs/internal/plans/agent_design_lab_execution.md) for qualified facts and open gaps.

## Design and adaptation boundary

Start with a small tool surface and compose extensions explicitly. This is not Pi's TypeScript runtime, TUI or full extension ecosystem. [Primary source](https://github.com/earendil-works/pi/tree/main/packages/coding-agent).

## Framework versus application

Four native Env tools plus verification_tools form the registry. The extension runs fixed controller checks in Docker and retains tested source digests as ArtifactRefs.

QitOS supplies model transactions/usage, tool permission/validation, Env execution, Session, ArtifactRef and Trajectory. The application supplies tasks, policy, independent acceptance checks and memory/skill selection. This iteration adds custom agent_factory composition, persistent skill revisions, full-body selection, explicit Memdir deletion and correct artifact data authority.

The core design increment is in agent.py below. The CLI shows configuration and resource ownership explicitly; evaluate.py is the controller checker. Tasks use repository-owned synthetic professional scenarios, not paper benchmarks or customer data.

## Install, configure and run

First install the QitOS wheel built from this iteration; the current PyPI release cannot stand in for unpublished APIs. Then install this project. Keep actual addresses and credentials outside Git. The private model file is a full qitos.agent configuration; this launcher selects only its model section, never an environment-variable key.

Use a new external directory for every run; resume reconstructs this project's factory and resolver.

The output default is 10,240 and may be raised in private model configuration. Task request/step/time guards come from configuration. validate does not call a model; --live is mandatory for execution. Docker failure must not silently fall back to the host. Retain unsuccessful results and human interventions.

## Verification, exercise and composition

Independent checks examine sources/numbers or executed code, not a model's success claim. Plan revisions, actual skill loading and child identities require separate mechanism evidence. Session restore is not filesystem rollback. Generated code executes only in the restricted Env.

Exercise: Install a different verifier that checks a CLI contract, without changing the Agent policy.

Composition: Reuse the verifier in Claude-like child review or the Voyager publish gate.

The required matrix is three tasks, three repetitions each. ReAct/PlanAct share tasks; static planning, no-memory and no-skills are explicit controls. A single pass is not a performance result. Raw traces stay private until redistribution and sanitization checks authorize a derived publication.

```bash
python -m pip install .
python -m qitos_lab_pi validate --config agent.yaml --root /tmp/lab-validation
python -m qitos_lab_pi run --config agent.yaml --model-config /private-config/model.yaml --credentials /private-config/credentials.yaml --root /private-runs/pi-attempt --task 0 --live
```
