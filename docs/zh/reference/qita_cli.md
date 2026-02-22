# qita（命令行参考）

## 命令

### `qita board`

启动 web 面板。

```bash
python -m qitos.qita board --logdir ./runs --host 127.0.0.1 --port 8765
```

### `qita replay`

回放单次 run。

```bash
python -m qitos.qita replay --run runs/<run_id>
```

### `qita export`

导出独立 HTML。

```bash
python -m qitos.qita export --run runs/<run_id> --html ./export/<run_id>.html
```

## Source Index

- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
- [tests/test_qita_cli.py](https://github.com/Qitor/qitos/blob/main/tests/test_qita_cli.py)
