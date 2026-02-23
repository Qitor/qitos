# qita Guide

## Goal

Use `qita` as your default run inspection tool: board, view, replay, and export.

## UI Snapshot

### qita board

![qita board](../assets/qita_board_snapshot.png)

### qita trajectory view

![qita trajectory view](../assets/qita_traj_snapshot.png)

## 0) First create at least one run

Run any example with trace enabled (default):

```bash
python examples/patterns/react.py --workspace ./playground
```

This usually creates run artifacts under `./runs/<run_id>/` with:

- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

## 1) Start board

```bash
qita board --logdir runs
```

Open URL printed by CLI (default: `http://127.0.0.1:8765/`).

Board provides:

1. run list and search/filter
2. run-level metrics and status
3. quick buttons: `view`, `replay`, `export raw`, `export html`

## 2) View one run (readable cards)

From board click `view`, or open directly:

```text
http://127.0.0.1:8765/run/<run_id>
```

In `view` page:

1. `Traj` tab for step-by-step cards
2. `Manifest` tab for run metadata
3. timeline and event sections
4. font scaling and fold/unfold controls

## 3) Replay one run in browser

CLI mode:

```bash
qita replay --run runs/<run_id>
```

This opens focused replay mode at:

```text
/replay/<run_id>
```

Use replay when you need to inspect temporal order of events and failures.

## 4) Export run artifacts

### Export raw JSON bundle

From board/view click `export raw`, or open:

```text
http://127.0.0.1:8765/export/raw/<run_id>
```

### Export standalone HTML

From board/view click `export html`, or CLI:

```bash
qita export --run runs/<run_id> --html ./report/<run_id>.html
```

Use this to share one run snapshot without requiring a live server.

## 5) Recommended workflow for debugging

1. run agent once
2. open board and locate failed run by `stop_reason`
3. open `view` and find first abnormal phase/event
4. use `replay` to confirm event ordering
5. export HTML for issue discussion or PR evidence

## 6) Common problems

1. board shows no runs
- ensure `--logdir` points to the directory containing run subfolders
- ensure each run folder has `manifest.json`

2. replay reports run not found
- pass full path to `--run`, e.g. `runs/<run_id>`

3. malformed event line
- parser tolerates invalid lines, but fix upstream event writer if this repeats

## If `qita` command is not found

If you installed QitOS without editable install, or your shell can't find console scripts, use:

```bash
python -m qitos.qita board --logdir runs
```

## Source Index

- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
- [tests/test_qita_cli.py](https://github.com/Qitor/qitos/blob/main/tests/test_qita_cli.py)
