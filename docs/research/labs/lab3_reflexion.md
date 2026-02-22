# Lab 3 - Upgrade PlanAct to Reflexion (30 min, with code)

## Goal

Add structured self-critique with evidence grounding, then measure quality vs cost.

---

## Part A: Define quality dimensions (5 min)

```python
quality_axes = {
    "grounding": "claims must be supported by evidence",
    "completeness": "important aspects should not be missing",
    "conciseness": "avoid superfluous claims",
}
print(quality_axes)
```

---

## Part B: Design reflection loop state (5 min)

```python
from dataclasses import dataclass, field
from typing import Any, Dict, List

from qitos import StateSchema

@dataclass
class ReflexionState(StateSchema):
    target_url: str = ""
    page_text: str = ""
    draft_answer: str = ""
    reflections: List[Dict[str, Any]] = field(default_factory=list)
    max_reflections: int = 2
```

---

## Part C: Implement structured reflexion (10 min)

### C1. Output contract

```python
REFLEXION_PROMPT = """Return valid JSON only:
{
  \"answer\": \"...\",
  \"citations\": [{\"source\": \"source_text\", \"quote\": \"exact supporting quote\"}],
  \"critique\": {
    \"missing\": [\"...\"],
    \"superfluous\": [\"...\"],
    \"grounding\": [\"...\"],
    \"needs_revision\": true
  }
}
"""
```

### C2. Robust JSON parse + loop control

```python
import json
from qitos import Decision

def reflect_once(llm, prompt: str):
    raw = llm([
        {"role": "system", "content": "Return valid JSON only."},
        {"role": "user", "content": prompt},
    ])
    text = str(raw).strip()
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s : e + 1])
        return None

class ReflexionAgent(...):
    def decide(self, state: ReflexionState, observation: dict):
        payload = reflect_once(self.llm, REFLEXION_PROMPT)
        if payload is None:
            return Decision.final("Failed to produce valid reflexion JSON output")
        state.draft_answer = str(payload.get("answer", "")).strip()
        state.reflections.append(payload)
        needs_revision = bool(payload.get("critique", {}).get("needs_revision", False))
        if needs_revision and len(state.reflections) <= state.max_reflections:
            return Decision.wait("reflexion_revision_cycle")
        return Decision.final(state.draft_answer)
```

---

## Part D: Run and evaluate (10 min)

```bash
python examples/patterns/reflexion.py --workspace ./playground --max-reflections 2 --max-steps 12
```

Evaluate:

1. quality improvements (groundedness/completeness/conciseness)
2. step/token cost
3. new failure modes (often JSON formatting/parsing)

---

## Source Index

- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/kit/parser/json_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/json_parser.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
