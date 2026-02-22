# QitOS（气）

<div class="qitos-hero">

QitOS 是一个面向研究与工程落地的 **Agent 内核框架**。

- 单主线：`AgentModule + Engine`
- 显式循环：`observe -> decide -> act -> reduce -> check_stop`
- 可复现：hooks + trace 作为一等公民

<div class="qitos-actions">
  <a class="qitos-btn qitos-btn-glow" href="zh/getting-started/">开始构建</a>
  <a class="qitos-btn" href="zh/research/kernel/">先读内核</a>
  <a class="qitos-btn" href="zh/builder/qita/">用 qita 复盘</a>
</div>

</div>

<div class="qitos-section">
<div class="qitos-grid">
  <div class="qitos-card">
    <h3>研究者</h3>
    <p>复现论文、做方法创新、在统一口径下做严格对比。</p>
    <p><a href="zh/research/kernel/">从内核开始</a></p>
  </div>
  <div class="qitos-card">
    <h3>开发者</h3>
    <p>快速跑通、接入工具与环境、稳定上线并可观测。</p>
    <p><a href="zh/getting-started/">从快速上手开始</a></p>
  </div>
  <div class="qitos-card">
    <h3>可观测与复盘</h3>
    <p>用 qita 做 board/view/replay/export 全链路分析。</p>
    <p><a href="zh/builder/qita/">打开 qita 使用指南</a></p>
  </div>
</div>
</div>

<div class="qitos-section">
<h2>2 分钟跑通</h2>

```bash
pip install -e .
```

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_key>"
```

```bash
python examples/patterns/react.py --workspace ./playground
```

<div class="qitos-actions">
  <a class="qitos-btn qitos-btn-glow" href="zh/builder/configuration/">配置模型</a>
  <a class="qitos-btn" href="research/labs/">查看教程</a>
</div>
</div>

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
