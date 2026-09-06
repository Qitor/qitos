# PlanAct research

Status: in development, not course-qualified. The working source below is not a claim of a passed 3×3 live matrix. See the [execution ledger](../../../docs/internal/plans/agent_design_lab_execution.md) for qualified facts and open gaps.

## Design and adaptation boundary

Separate planning from execution and revise plans with feedback. This implements a runtime teaching adaptation, not the paper's planner training or benchmark result. [Primary source](https://arxiv.org/abs/2503.09572).

## Framework versus application

A persisted phase and plan_version distinguish roles. revise_plan is a canonical tool call, not an untracked planner SDK call. The static variant disables automatic return to planning.

QitOS supplies model transactions/usage, tool permission/validation, Env execution, Session, ArtifactRef and Trajectory. The application supplies tasks, policy, independent acceptance checks and memory/skill selection. This iteration adds custom agent_factory composition, persistent skill revisions, full-body selection, explicit Memdir deletion and correct artifact data authority.

The core design increment is in agent.py below. The CLI shows configuration and resource ownership explicitly; evaluate.py is the controller checker. Tasks use repository-owned synthetic professional scenarios, not paper benchmarks or customer data.

## Install, configure and run

First install the QitOS wheel built from this iteration; the current PyPI release cannot stand in for unpublished APIs. Then install this project. Keep actual addresses and credentials outside Git. The private model file is a full qitos.agent configuration; this launcher selects only its model section, never an environment-variable key.

Use a new external directory for every run; resume reconstructs this project's factory and resolver.

The output default is 10,240 and may be raised in private model configuration. Task request/step/time guards come from configuration. validate does not call a model; --live is mandatory for execution. Docker failure must not silently fall back to the host. Retain unsuccessful results and human interventions.

## Verification, exercise and composition

Independent checks examine sources/numbers or executed code, not a model's success claim. Plan revisions, actual skill loading and child identities require separate mechanism evidence. Session restore is not filesystem rollback. Generated code executes only in the restricted Env.

Exercise: Replace always-replan with an evidence-triggered policy and compare failures as well as cost.

Composition: Use the notebook's memory adapter and a separately installed verification extension; neither should modify Engine.

The required matrix is three tasks, three repetitions each. ReAct/PlanAct share tasks; static planning, no-memory and no-skills are explicit controls. A single pass is not a performance result. Raw traces stay private until redistribution and sanitization checks authorize a derived publication.

```bash
python -m pip install .
python -m qitos_lab_planact validate --config agent.yaml --root /tmp/lab-validation
python -m qitos_lab_planact run --config agent.yaml --model-config /private-config/model.yaml --credentials /private-config/credentials.yaml --root /private-runs/planact-attempt --task 0 --live
```
