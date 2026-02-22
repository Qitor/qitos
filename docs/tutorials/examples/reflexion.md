# Reflexion Example Walkthrough (Actor-Critic With Grounded Self-Reflection)

## What this agent is

`examples/patterns/reflexion.py` implements a Reflexion-style actor-critic loop:

- the agent drafts an answer
- the agent critiques the draft against external evidence (source text)
- the agent revises, repeating for a bounded number of cycles

This example intentionally uses a **strict JSON protocol** for reflection payloads.

## Core idea

Reflexion is not “add another prompt”. It is:

1. forcing structured critique (missing/superfluous/grounding)
2. grounding critique in external evidence (citations)
3. turning critique into a revision policy

In QitOS terms:

- the “critic loop” can be implemented as:
  - a separate `Critic` module (Engine-level), or
  - a policy encoded in `AgentModule.decide(...)` (this example)

This example chooses the second option to keep it self-contained and explicit.

## Method-by-method design

### State: keep evidence, draft, and reflections

Design principle:

- If reflection is real, you must store the critique artifacts.

What the example does:

- stores `page_html`, `page_text` as external evidence
- stores `draft_answer` and `reflections` (each is a JSON object)
- stores `max_reflections` to bound the loop

### `decide`: a staged pipeline

Design principle:

- Reflexion needs a deterministic staging gate:
  - fetch -> extract -> reflect/revise -> finalize

What the example does:

1. If no HTML: `Decision.act(http_get)`
2. If no text: `Decision.act(extract_web_text)`
3. Else: call `_reflect(...)` (LLM) to produce structured JSON
4. If `needs_revision` and cycles remain: `Decision.wait(...)` to loop again
5. Else: `Decision.final(...)` with answer + citations

### `_reflect`: strict output protocol as a research control

Design principle:

- If the output is not structured, you cannot evaluate it consistently.

What the example does:

- system instruction: “Return valid JSON only.”
- requires `citations` with **exact supporting quote**
- requires “missing” and “superfluous” lists to avoid vague critiques

### `reduce`: only moves tool outputs into evidence fields

Design principle:

- Keep `reduce` as a state transition; don’t hide policy here.

What the example does:

- assigns `page_html` from `http_get`
- assigns `page_text` from `extract_web_text`
- policy logic (revision cycles) stays in `decide`

## What to modify to make it SOTA-ish

1. Add a verifier:
   - run a second pass to validate that citations appear in the source text
2. Add stop criteria:
   - stop if critique says `needs_revision=false` twice in a row
3. Externalize critic to Engine:
   - use `Engine(critics=[...])` to decouple reflection from actor policy

## Source Index

- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/kit/tool/web.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/web.py)
- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
