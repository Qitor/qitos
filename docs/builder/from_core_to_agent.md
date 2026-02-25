# From Core to Agent

## Goal

Build a practical agent by inheriting core contracts, with clear implementation milestones.

## Milestone 1: define state and agent shell

1. create a `StateSchema` subclass with only essential fields
2. implement `init_state`, `prepare`, `reduce`
3. return `Decision.final(...)` first to verify loop plumbing

## Milestone 2: wire tools and parser

1. register one simple tool
2. attach parser (for LLM output mode)
3. run one `Decision.act(...)` path and verify action result enters state

## Milestone 3: switch to model-driven decisions

1. implement `build_system_prompt`
2. implement `prepare`
3. set `decide` to return `None`
4. verify model output can be parsed to valid `Decision`

## Milestone 4: add env + memory

1. choose Env backend (`HostEnv` first)
2. set `build_memory_query` for bounded context
3. verify trace includes memory and env payload

## Milestone 5: harden runtime

1. configure budgets
2. add hook-based observability
3. add two or three regression tasks

## Minimal production-ready run command

```bash
python examples/real/coding_agent.py \
  --model-base-url "https://api.siliconflow.cn/v1/" \
  --api-key "<your_api_key>" \
  --model-name "Qwen/Qwen3-8B" \
  --workspace ./playground
```

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/real/coding_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/coding_agent.py)
