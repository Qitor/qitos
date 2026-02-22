# Examples

Examples are organized by learning depth.

## Structure

- `examples/quickstart/`
  - minimal runnable agent in ~50 lines.
- `examples/patterns/`
  - focused algorithm patterns: ReAct / Plan-Act / ToT / Reflexion.
- `examples/real/`
  - practical end-to-end agents: coding / SWE / computer-use / EPUB.

## API Key (local only)

Never commit API keys.

```bash
export OPENAI_API_KEY="your_api_key"
# or
export QITOS_API_KEY="your_api_key"
```

## Quickstart

```bash
python examples/quickstart/minimal_agent.py
```

## Patterns

```bash
python examples/patterns/react.py --workspace /tmp/qitos_react
python examples/patterns/planact.py --workspace /tmp/qitos_planact
python examples/patterns/tot.py --workspace /tmp/qitos_tot
python examples/patterns/reflexion.py --workspace /tmp/qitos_reflexion
```

Notes for Reflexion pattern:
- The actor must critique each draft with explicit `missing` and `superfluous` lists.
- The critique must be grounded in external data with explicit citations.
- The agent revises until critique says no further revision is needed (or max reflections reached).

## Real Agents

```bash
python examples/real/coding_agent.py --workspace /tmp/qitos_coding
python examples/real/swe_agent.py --workspace /tmp/qitos_swe
python examples/real/computer_use_agent.py --workspace /tmp/qitos_computer
python examples/real/epub_reader_agent.py --workspace /tmp/qitos_epub
python examples/real/open_deep_research_gaia_agent.py --workspace /tmp/qitos_gaia --gaia-from-local
```

## Common CLI flags

All pattern/real examples support:
- `--workspace`
- `--model-base-url`
- `--api-key`
- `--model-name`
- `--temperature`
- `--max-tokens`
- `--theme`
- `--trace-logdir`
- `--trace-prefix`
- `--disable-trace`
- `--disable-render`
