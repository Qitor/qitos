# qita 使用指南

## 目标

把 `qita` 作为你默认的运行分析工具，形成完整闭环：board、view、replay、export。

## 界面截图

### qita board

![qita board](../../assets/qita_board_snapshot.png)

### qita 轨迹视图

![qita trajectory view](../../assets/qita_traj_snapshot.png)

## 0）先生成至少一次运行产物

先跑一个示例（默认会写 trace）：

```bash
python examples/patterns/react.py --workspace ./playground
```

通常会在 `./runs/<run_id>/` 下看到：

- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

## 1）启动 board

```bash
qita board --logdir runs
```

打开 CLI 输出的地址（默认 `http://127.0.0.1:8765/`）。

board 页面能做：

1. 检索与筛选 run
2. 查看 run 级统计与状态
3. 一键进入 `view` / `replay`
4. 一键导出 raw / html

## 2）查看单次运行（view）

可以在 board 点 `view`，也可以直接访问：

```text
http://127.0.0.1:8765/run/<run_id>
```

在 view 页面：

1. `Traj` 标签看 step 卡片化轨迹
2. `Manifest` 标签看运行元数据
3. 看 phase 时间线、事件详情
4. 用字体放大/折叠提高可读性

## 3）在浏览器里回放（replay）

命令行方式：

```bash
qita replay --run runs/<run_id>
```

会进入聚焦回放页面：

```text
/replay/<run_id>
```

适合定位“先后顺序”相关问题，比如先报错还是先进入 stop。

## 4）导出运行结果

### 导出原始 JSON

在 board/view 点 `export raw`，或直接访问：

```text
http://127.0.0.1:8765/export/raw/<run_id>
```

### 导出独立 HTML

在 board/view 点 `export html`，或命令行：

```bash
qita export --run runs/<run_id> --html ./report/<run_id>.html
```

这个 HTML 可单文件分享，适合评审与复盘。

## 5）推荐排查流程

1. 先看 board，按 `stop_reason` 找失败 run
2. 进 view，定位首个异常 phase/event
3. 用 replay 确认事件时序
4. 导出 html，附到 issue/PR

## 6）常见问题

1. board 空白看不到 runs
- 检查 `--logdir` 是否指向 run 根目录
- 检查每个 run 子目录是否有 `manifest.json`

2. replay 提示 run not found
- `--run` 要传完整目录，如 `runs/<run_id>`

3. 事件里有非法 JSON 行
- 当前会容错读取，但需要回头修复事件写入链路

## 如果找不到 `qita` 命令

如果你的环境没有把 console scripts 加入 PATH，可以用模块方式启动：

```bash
python -m qitos.qita board --logdir runs
```

## Source Index

- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
- [tests/test_qita_cli.py](https://github.com/Qitor/qitos/blob/main/tests/test_qita_cli.py)
