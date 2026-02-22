# 配置与 API Key

## 目标

让你在 5 分钟内完成模型配置并成功跑通示例。

## 支持的配置入口

当前示例（`examples/common.py`）支持两种方式：

1. 命令行参数
2. 环境变量

API Key 优先级：

1. `--api-key`
2. `OPENAI_API_KEY`
3. `QITOS_API_KEY`

## 默认参数（示例层）

- `--model-base-url` 默认：`https://api.siliconflow.cn/v1/`
- `--model-name` 默认：`Qwen/Qwen3-8B`
- `--temperature` 默认：`0.2`
- `--max-tokens` 默认：`2048`

## 推荐配置方式（最快）

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"
```

## 不要把 API Key 提交到 git

不要在示例代码里硬编码 key，更不要提交到 GitHub。

推荐做法：

- 在 shell 环境变量里导出，或
- 用本地 `.env` 并在 shell 启动时加载（不要提交 `.env`）

然后运行：

```bash
python examples/patterns/react.py \
  --model-base-url "$OPENAI_BASE_URL" \
  --model-name "Qwen/Qwen3-8B" \
  --workspace ./playground
```

## 仅命令行配置（不依赖环境变量）

```bash
python examples/patterns/react.py \
  --model-base-url "https://api.siliconflow.cn/v1/" \
  --api-key "<your_api_key>" \
  --model-name "Qwen/Qwen3-8B" \
  --workspace ./playground
```

## 快速自检

```bash
python examples/patterns/react.py --max-steps 1 --workspace ./playground
```

如果配置正确，应当看到：

1. 终端渲染中出现模型决策过程
2. 没有 `Missing API key` 报错
3. `runs/` 下生成 trace（除非加了 `--disable-trace`）

## 常见报错与处理

1. `Missing API key...`
- 请设置 `--api-key` 或 `OPENAI_API_KEY` / `QITOS_API_KEY`

2. 401/403
- key 无效、过期，或不匹配当前 endpoint

3. 404 / model not found
- `--model-name` 与提供方支持列表不一致

4. timeout
- endpoint 不可达、网络代理问题、或服务端拥塞

## Source Index

- [examples/common.py](https://github.com/Qitor/qitos/blob/main/examples/common.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/models/openai.py](https://github.com/Qitor/qitos/blob/main/qitos/models/openai.py)
