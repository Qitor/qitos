# History

## Goal

Clarify message-history ownership and usage in QitOS.

## Ownership

History belongs to `AgentModule` (`self.history`) or falls back to engine runtime history.

## History contract

`History` provides:

- `append(message)`
- `retrieve(query, state, observation)`
- `summarize(max_items)`
- `reset(run_id)`

## Engine usage

In default model path (`decide -> None`), Engine assembles messages as:

1. `system` (optional)
2. selected `history` messages (by `history_policy`)
3. current `user` message from `prepare(state)`

Engine appends current user/assistant turns into history.

Typical history stream:

- `system`
- `user`
- `assistant`
- `user`
- `assistant`
- ...

## HistoryPolicy

Configure from Engine:

- `roles`
- `max_messages`
- `step_window`

## Source Index

- [qitos/core/history.py](https://github.com/Qitor/qitos/blob/main/qitos/core/history.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/kit/history/window_history.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/history/window_history.py)
