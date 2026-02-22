# Why QitOS

## Goal

Clarify where QitOS is intentionally strong and where it is intentionally not trying to compete.

## QitOS design stance

QitOS chooses **research-grade runtime clarity** over maximal abstraction breadth.

1. One kernel mainline instead of many top-level frameworks.
2. Explicit step phases for inspectable behavior.
3. Standardized hooks and trace payloads for reproducible studies.

## If this is your priority

- Fast low-code app assembly by non-engineers:
  platforms like Dify/Langflow may be better first choice.

- Deep method iteration and controlled ablations:
  QitOS should fit better.

## Positioning

QitOS is a kernel for agent R&D and advanced builders, not a full app platform replacement.

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
