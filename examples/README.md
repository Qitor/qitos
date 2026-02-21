# Examples

All examples are practical agent workflows and share one config file:
- `examples/config.yaml`

Config supports env placeholders:
- `${OPENAI_BASE_URL}`
- `${OPENAI_API_KEY}`

## 1) Coding Agent (memory.md ReAct + reflection)

```bash
python examples/coding_agent.py --config examples/config.yaml --workspace /tmp/qitos_coding
```

What it demonstrates:
- Local code editing with `EditorToolSet`
- Verification with `run_command`
- Persistent `memory.md` via `MarkdownFileMemory`
- Self-correction loop with `ReActSelfReflectionCritic`

## 2) SWE Agent (dynamic planning)

```bash
python examples/swe_dynamic_planning_agent.py --config examples/config.yaml --workspace /tmp/qitos_swe
```

What it demonstrates:
- LLM-generated numbered plans
- Plan-step execution and re-planning
- Branch candidate decisions + `DynamicTreeSearch`

## 3) Computer-Use Agent (ReAct)

```bash
python examples/computer_use_agent.py --config examples/config.yaml --workspace /tmp/qitos_computer
```

What it demonstrates:
- Web fetch with `http_get`
- HTML-to-text extraction with `extract_web_text`
- Report writing with `write_file`

## 4) EPUB Reader Agent (Tree-of-Thought)

```bash
python examples/epub_reader_tot_agent.py --config examples/config.yaml --workspace /tmp/qitos_epub
```

What it demonstrates:
- ToT-style branch thoughts emitted as `Decision.branch(...)`
- Search/selection via `DynamicTreeSearch`
- EPUB chapter discovery, search, and targeted reading with `EpubToolSet`

## Notes

- Provide a real EPUB file for the EPUB example (default: `book.epub` under the workspace).
- If `--workspace` is omitted, examples use a temporary directory.
- Enable render streaming in `examples/config.yaml` to get step-by-step terminal traces and `render_events.jsonl`.
- Render themes are configurable via `render.theme`:
  - `research` (default)
  - `minimal`
  - `neon`
