# QitOS

![QitOS Logo](assets/logo.png)

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.github.io/qitos-0A66C2)](https://qitor.github.io/qitos/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

**QitOS 是面向严肃智能体研发的 research-first 框架。**  
它提供统一执行内核、可组合模块与 benchmark 原生工作流，让你从想法快速走到可复现结果，而不必重写整套基础设施。

- English README: [README.md](README.md)
- 文档站点: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)

## 为什么团队选择 QitOS

- **研究优先**：天然适配 ReAct、Plan-Act、ToT、Reflexion 及自定义 scaffolding 快速迭代。
- **统一内核**：`AgentModule + Engine`，生命周期稳定、可推理、易扩展。
- **模块化架构**：`core`、`engine`、`kit`、`benchmark`、`evaluate` 按需组合。
- **生态兼容**：可自然接入 OpenAI 兼容模型接口、主机环境与工具注册机制。
- **Benchmark 原生**：统一支持 GAIA、Tau-Bench、CyBench。
- **生产级可观测性**：trace、hooks、回放、导出由 `qita` 一体化提供。

## 核心优势

```text
Task -> Engine.run(...)
     -> prepare -> decide -> act -> reduce -> check_stop -> ...
     -> hooks + trace + replay + metrics
```

一套架构同时覆盖研究、评测与真实部署。

## 安装

```bash
pip install qitos
```

开发模式：

```bash
pip install -e .
pip install -e ".[models,yaml,benchmarks]"
```

## 快速开始

运行最小端到端链路：

```bash
python examples/quickstart/minimal_agent.py
```

运行模式化智能体示例：

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"
python examples/patterns/react.py --workspace ./playground
```

查看轨迹与统计：

```bash
qita board --logdir runs
```

## 你可以构建什么

模式示例：
- `examples/patterns/react.py`
- `examples/patterns/planact.py`
- `examples/patterns/tot.py`
- `examples/patterns/reflexion.py`

真实场景：
- `examples/real/coding_agent.py`
- `examples/real/swe_agent.py`
- `examples/real/computer_use_agent.py`
- `examples/real/epub_reader_agent.py`

## Benchmark 与评测

QitOS 统一链路：

`数据样本 -> adapter -> Task -> Engine -> evaluate -> metric report`

内置适配：
- `qitos.benchmark.gaia`
- `qitos.benchmark.tau_bench`
- `qitos.benchmark.cybench`

评测体系：
- `qitos.evaluate` 负责单任务结果判定
- `qitos.metric` 负责基准级指标汇总
- `qitos.kit` 提供 rule-based / DSL-based / model-based evaluator 与常用 metrics

## qita 可观测性

- `qita board`：运行总览与统计
- `qita view`：结构化轨迹查看
- `qita replay`：执行过程回放
- `qita export`：导出 JSON / HTML 工件

## 项目结构

- `qitos/core/`：接口与核心契约
- `qitos/engine/`：执行内核
- `qitos/kit/`：可复用模块（工具、解析、规划、记忆、评测）
- `qitos/benchmark/`：benchmark 适配层
- `qitos/qita/`：轨迹工具链

## 文档

- 主文档: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- API 参考: [https://qitor.github.io/qitos/reference/api_generated/](https://qitor.github.io/qitos/reference/api_generated/)
- 中文文档: [https://qitor.github.io/qitos/zh/](https://qitor.github.io/qitos/zh/)

## License

MIT，见 [LICENSE](LICENSE)。
