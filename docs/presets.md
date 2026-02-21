# Presets

Preset modules are composable building blocks that strictly follow canonical kernel contracts.

## Directory Convention

- `qitos/presets/policies.py`
- `qitos/presets/parsers.py`
- `qitos/presets/memories.py`
- `qitos/presets/search.py`
- `qitos/presets/critics.py`
- `qitos/presets/toolkits.py`
- `qitos/presets/registry.py`

## Composition Matrix

| Policy | Parser | Memory | Search | Critic | Toolkit | Works |
|---|---|---|---|---|---|---|
| `react_arithmetic` | `json` | `window` | `greedy` | `pass_through` | `math` | Yes |
| `react_arithmetic` | `react_text` | `summary` | `greedy` | `pass_through` | `math` | Yes |
| `react_arithmetic` | `xml` | `vector` | `greedy` | `pass_through` | `math` | Yes |

## Design Rules

- Presets compose through public contracts only.
- Presets cannot rely on hidden runtime internals.
- Presets must be discoverable through `qitos.presets.build_registry()`.
