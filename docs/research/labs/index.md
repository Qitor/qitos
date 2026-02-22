# 30-Min Labs (Build-From-Scratch Track)

These labs assume you already learned the QitOS core concepts.

The objective is not to read existing code first.
The objective is to **design and build** agent methods using QitOS contracts, then compare them with reproducible evidence.

## You will learn

1. how to define a research question in agent terms
2. how to implement strategy upgrades on one stable kernel
3. how to evaluate variants with consistent trace/metric criteria

## Setup

```bash
pip install -e .
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_key>"
```

If not configured yet:

- [Configuration & API Keys](../../builder/configuration.md)

## Sequence

1. [Lab 1 - Build ReAct Baseline](lab1_react.md)
2. [Lab 2 - Upgrade ReAct to PlanAct](lab2_planact.md)
3. [Lab 3 - Upgrade PlanAct to Reflexion](lab3_reflexion.md)

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
