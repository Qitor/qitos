# 工具与环境

## 目标

让工具语义稳定、执行后端可替换，从而获得更好的可移植性。

## 心智模型

- **Tool**：逻辑能力（如读写文件、执行命令、抓网页）
- **Env**：执行后端（Host、Docker、Repo 等）

Tool 声明所需 ops group，Env 提供对应 capability。

## 教程：同一工具切换环境

1. 定义一个依赖 `file` ops 的工具。
2. 在 `HostEnv` 下运行。
3. 切到 `DockerEnv` 再运行。
4. 对比 trace，验证行为一致性。

## 常见故障

1. `ENV_CAPABILITY_MISMATCH`
- 当前 Env 缺少工具需要的 ops group。

2. Host 能跑，Docker 失败
- 通常是路径映射或工作目录配置问题。

3. 命令执行不稳定
- 收紧 timeout，限制命令模板输入。

## Source Index

- [qitos/core/tool.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool.py)
- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/engine/action_executor.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/action_executor.py)
- [qitos/kit/env/host_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/host_env.py)
- [qitos/kit/env/docker_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/docker_env.py)
- [qitos/kit/tool/editor.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/editor.py)
