# Lab 3 - 从 PlanAct 升级到 Reflexion（30 分钟，含代码分步）

## 适用场景

你希望在 PlanAct 基础上提升答案质量与可信度，尤其是信息提取/总结类任务。

## 学习目标

1. 引入“证据约束 + 自反思”循环。
2. 让模型输出结构化批判信息。
3. 评估质量提升与成本上升的权衡。

---

## Part A：定义质量维度（5 分钟）

先明确本实验的质量维度：

```python
quality_axes = {
    "grounding": "claims should be supported by source evidence",
    "completeness": "important aspects should not be missing",
    "conciseness": "avoid superfluous claims",
}
print(quality_axes)
```

---

## Part B：设计反思循环状态（5 分钟）

```python
from dataclasses import dataclass, field
from typing import Dict, Any, List
from qitos import StateSchema

@dataclass
class ReflexionState(StateSchema):
    target_url: str = ""
    page_text: str = ""
    draft_answer: str = ""
    reflections: List[Dict[str, Any]] = field(default_factory=list)
    max_reflections: int = 2
```

注意：`max_reflections` 是防止无限循环的关键。

---

## Part C：实现结构化反思策略（10 分钟）

### C1. 反思提示词与 JSON 契约

```python
REFLEXION_PROMPT = """Return valid JSON only:
{
  "answer": "...",
  "citations": [{"source": "...", "quote": "..."}],
  "critique": {
    "missing": ["..."],
    "superfluous": ["..."],
    "grounding": ["..."],
    "needs_revision": true
  }
}
"""
```

### C2. 解析与循环控制

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
            return json.loads(text[s:e+1])
        return None

class ReflexionAgent(...):
    def decide(self, state: ReflexionState, observation: dict):
        payload = reflect_once(self.llm, REFLEXION_PROMPT)
        if payload is None:
            return Decision.final("Failed to produce valid reflexion JSON output")
        state.draft_answer = str(payload.get("answer", ""))
        state.reflections.append(payload)
        needs_revision = bool(payload.get("critique", {}).get("needs_revision", False))
        if needs_revision and len(state.reflections) <= state.max_reflections:
            return Decision.wait("reflexion_revision_cycle")
        return Decision.final(state.draft_answer)
```

---

## Part D：运行与质量-成本评估（10 分钟）

### D1. 运行

```bash
python examples/patterns/reflexion.py --workspace ./playground --max-reflections 2 --max-steps 12
```

### D2. 评估片段（质量 + 成本）

```python
import json
from pathlib import Path

m = json.loads(Path("runs/reflexion_run/manifest.json").read_text(encoding="utf-8"))
s = m.get("summary", {})
print("stop_reason:", s.get("stop_reason"))
print("steps:", s.get("steps"))
print("final_result preview:", str(s.get("final_result", ""))[:200])
```

与 PlanAct 对比时至少看：

1. 结果质量是否明显提升
2. 步数与 token 成本是否可接受
3. 新失败是否主要来自 JSON 解析与格式约束

---

## Source Index

- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/kit/critic/self_reflection.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/critic/self_reflection.py)
- [qitos/engine/critic.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/critic.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
