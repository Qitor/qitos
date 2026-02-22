# Decisions & Actions

## Goal

Understand the normalized runtime intent layer used by QitOS.

## Decision

A `Decision` describes what the agent wants to do next:

- `act`: execute tool actions
- `wait`: do nothing but continue
- `final`: stop with final answer

### Typical lifecycle

1. model outputs a text payload
2. parser converts it to `Decision`
3. engine validates and executes

## Action

An `Action` is a normalized tool invocation:

- `name`: tool name
- `args`: keyword arguments
- `max_retries`, `timeout_s`: execution policy

## Practical rule

If you want the Engine to call the model, return `None` from `AgentModule.decide`.

## Source Index

- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
- [qitos/core/action.py](https://github.com/Qitor/qitos/blob/main/qitos/core/action.py)
- [qitos/engine/action_executor.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/action_executor.py)
