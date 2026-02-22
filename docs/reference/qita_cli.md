# qita (CLI Reference)

## Commands

### `qita board`

Start the web UI.

```bash
python -m qitos.qita board --logdir ./runs --host 127.0.0.1 --port 8765
```

### `qita replay`

Open one run in replay mode.

```bash
python -m qitos.qita replay --run runs/<run_id>
```

### `qita export`

Export one run to standalone HTML.

```bash
python -m qitos.qita export --run runs/<run_id> --html ./export/<run_id>.html
```

## Source Index

- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
- [tests/test_qita_cli.py](https://github.com/Qitor/qitos/blob/main/tests/test_qita_cli.py)
