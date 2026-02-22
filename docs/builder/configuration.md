# Configuration & API Keys

## Goal

Make examples runnable in under 5 minutes with explicit model configuration.

## Supported input methods

QitOS examples (via `examples/common.py`) support:

1. CLI args
2. Environment variables

Priority for API key is:

1. `--api-key`
2. `OPENAI_API_KEY`
3. `QITOS_API_KEY`

## Default model-related args

- `--model-base-url` default: `https://api.siliconflow.cn/v1/`
- `--model-name` default: `Qwen/Qwen3-8B`
- `--temperature` default: `0.2`
- `--max-tokens` default: `2048`

## Fastest setup (recommended)

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"
```

## Keep your API key out of git

Do not hardcode keys in examples or commit them to Git.

Recommended:

- export them in your shell profile, or
- use a local `.env` file and load it in your shell (do not commit `.env`)

Then run with explicit model endpoint:

```bash
python examples/patterns/react.py \
  --model-base-url "$OPENAI_BASE_URL" \
  --model-name "Qwen/Qwen3-8B" \
  --workspace ./playground
```

## Using CLI-only config (no env vars)

```bash
python examples/patterns/react.py \
  --model-base-url "https://api.siliconflow.cn/v1/" \
  --api-key "<your_api_key>" \
  --model-name "Qwen/Qwen3-8B" \
  --workspace ./playground
```

## Verify your config quickly

Run:

```bash
python examples/patterns/react.py --max-steps 1 --workspace ./playground
```

If config is correct, you should see:

1. model call activity in render output
2. no `Missing API key` exception
3. trace artifacts in `runs/` (unless `--disable-trace`)

## Common errors

1. `Missing API key...`
- set `--api-key` or `OPENAI_API_KEY`/`QITOS_API_KEY`

2. request 401/403
- key invalid or endpoint does not accept this key

3. request 404/model not found
- wrong `--model-name` for that provider

4. timeout
- endpoint unavailable, network/proxy issue, or too strict timeout in provider

## Source Index

- [examples/common.py](https://github.com/Qitor/qitos/blob/main/examples/common.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/models/openai.py](https://github.com/Qitor/qitos/blob/main/qitos/models/openai.py)
