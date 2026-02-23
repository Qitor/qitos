# QitOS

<div class="qitos-hero">

QitOS is a research-first **agentic kernel** for modular and reproducible agent workflows.

- One mainline: `AgentModule + Engine`
- Explicit loop: `observe -> decide -> act -> reduce -> check_stop`
- Reproducible: hooks + trace as first-class contracts

<div class="qitos-actions">
  <a class="qitos-btn qitos-btn-glow" href="getting-started/">Start Building</a>
  <a class="qitos-btn" href="research/kernel/">Learn the Kernel</a>
  <a class="qitos-btn" href="builder/qita/">Inspect with qita</a>
</div>

</div>

<div class="qitos-section">
<div class="qitos-grid">
  <div class="qitos-card">
    <h3>Researchers</h3>
    <p>Reproduce papers, design new methods, compare variants rigorously.</p>
    <p><a href="research/kernel/">Start with Kernel</a></p>
  </div>
  <div class="qitos-card">
    <h3>Builders</h3>
    <p>Get running fast, integrate tools/env, ship stable behavior.</p>
    <p><a href="getting-started/">Start with Getting Started</a></p>
  </div>
  <div class="qitos-card">
    <h3>Observability</h3>
    <p>Inspect every run with qita board/view/replay/export.</p>
    <p><a href="builder/qita/">Open qita Guide</a></p>
  </div>
  <div class="qitos-card">
    <h3>Benchmark Ready</h3>
    <p>GAIA is already adapted through qitos.benchmark -> Task.</p>
    <p><a href="builder/benchmark_gaia/">Run GAIA with QitOS</a></p>
  </div>
</div>
</div>

<div class="qitos-section">
<h2>Run in 2 Minutes</h2>

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
  <a class="qitos-btn qitos-btn-glow" href="builder/configuration/">Configure Model</a>
  <a class="qitos-btn" href="tutorials/examples/">Read Walkthroughs</a>
</div>
</div>

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
