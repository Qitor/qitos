# Examples

`examples/` is canonical learning material, not a product showcase.

The beginner path is installation → qit new → canonical configuration → Session
→ result/artifact/Trajectory inspection → recovery or extension.
Follow [Quickstart](../docs/quickstart.mdx) or [中文](../docs/zh/quickstart.mdx).

## Directory Map

- `examples/tutorials/`: complete offline Session and real Docker lessons.
- `examples/quickstart/`: compatible host coding demo; not the beginner isolation path.
- `examples/patterns/`: advanced method examples; inspect their host/tool policy.
- `examples/real/`: application teaching examples, not blanket provider qualification.
- `examples/benchmarks/`: benchmark recipe adapters.

## Recommended First Run Order

Install the exact G5 source before running qit, copy the complete tutorials
folder, then run session_walkthrough.py create and restore as documented.
The fake provider calls only trusted arithmetic functions; host is not a sandbox.
See tutorials/index for the eight units and explicit prerequisites.

## Benchmark wrappers

Benchmark wrappers:

```bash
python examples/benchmarks/gaia_eval.py --help
python examples/benchmarks/tau_bench_eval.py --help
python examples/benchmarks/cybench_eval.py --help
```

## Examples Policy

- One concept per file.
- No heavy hidden dependencies.
- No local absolute paths.
- No product clone as a canonical example.
- Benchmark wrappers call framework recipes/adapters and do not own canonical logic.
- Security-sensitive workflows are opt-in and not part of the quickstart.

## Full Applications

Full applications live in `qitos-zoo`, including:

- `qitos-coder`: a Claude Code-inspired coding agent built with QitOS.
- `qitos-cyber-agent`: a PentAGI-inspired cybersecurity agent built with QitOS.

Some product-like files remain temporarily in `examples/real/` with migration banners while the zoo repository is seeded from `plans/qitos_zoo_migration/`.

## Web-first notes project

`examples/tutorials/notes/` is the source for the complete files displayed on the
Quickstart and core learning pages. Every page includes its dependencies; users
can copy from the webpage without cloning this directory. Start with notes.py,
then custom_agent.py, parallel.py, lifecycle.py, context.py, sandbox.py,
multi_agent.py/handoff.py, inspect_run.py and provider_extension.py. real_notes.py
validates without credentials by default; --live is a deliberate model request.
