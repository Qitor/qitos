# Env 与能力组（Ops）

## 目标

理解 QitOS 如何把“工具语义”与“执行后端”解耦。

## 心智模型

- Tool 声明需要的 ops group（如 `file`、`process`）。
- Env 提供对应 ops group 的具体实现。

同一工具可以在 host/docker/repo 等后端运行。

## 为什么要有 ops groups

如果一个工具要读写文件，你不希望它在所有地方都直接 `open(...)`。
更好的做法是：工具只表达“需要文件能力”，具体怎么执行由 Env 决定。

这让你能同时支持：

- 本地开发用 `HostEnv`
- 沙箱执行用 `DockerEnv`
- 未来的远程/模拟环境（VM、k8s、浏览器沙箱等）

## 示例：同一个文件工具可跑在 host 或 docker

```python
from qitos import tool

@tool(name="read_text", required_ops=["file"])
def read_text(path: str, file_ops) -> str:
    # 当 Env 提供 "file" ops group 时，Engine 会自动注入 file_ops。
    return file_ops.read_text(path)
```

当你用 `HostEnv` 运行时，`file_ops` 指向宿主机文件系统操作。
当你用 `DockerEnv` 运行时，`file_ops` 会映射到容器内的文件系统操作。

## 预检行为

如果工具需要 ops 但没有提供 env，Engine 会在预检阶段停止并给出 `ENV_CAPABILITY_MISMATCH`。

## Source Index

- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/kit/env/host_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/host_env.py)
- [qitos/kit/env/docker_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/docker_env.py)
- [tests/test_env_host_and_engine_interpretation.py](https://github.com/Qitor/qitos/blob/main/tests/test_env_host_and_engine_interpretation.py)
