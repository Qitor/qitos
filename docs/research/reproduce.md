# Reproduce Paper Agents

## Goal

Reproduce known agent styles with minimal boilerplate and controlled experiment settings.

## Available pattern examples in this repo

- ReAct: `examples/patterns/react.py`
- PlanAct: `examples/patterns/planact.py`
- Reflexion-style: `examples/patterns/reflexion.py`
- Tree-of-Thought style: `examples/patterns/tot.py`

## Example walkthroughs (recommended)

If you want to reproduce a paper pattern or design a new variant, start with the walkthroughs:

- [ReAct Walkthrough](../tutorials/examples/react.md)
- [PlanAct Walkthrough](../tutorials/examples/planact.md)
- [Reflexion Walkthrough](../tutorials/examples/reflexion.md)
- [Tree-of-Thought Walkthrough](../tutorials/examples/tot.md)

## Tutorial: ReAct to PlanAct in 3 steps

### Step 1: run baseline ReAct

```bash
python examples/patterns/react.py
```

### Step 2: switch to PlanAct

```bash
python examples/patterns/planact.py
```

### Step 3: compare traces

Compare these fields in manifests/events:

1. `summary.stop_reason`
2. `summary.steps`
3. per-step `DECIDE` payload patterns
4. failure report structure

## Tutorial: reflexion loop

Run:

```bash
python examples/patterns/reflexion.py
```

Check whether critic outputs produce:

1. concrete missing/superfluous points
2. grounded feedback using available evidence
3. useful next-step behavior changes

## Reproduction quality bar

1. Fixed task set.
2. Fixed budget.
3. Logged model ID and parser.
4. At least 3 repeated runs for variance checks.
5. Report both success rate and failure taxonomy.

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [examples/patterns/tot.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/tot.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/kit/critic/self_reflection.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/critic/self_reflection.py)
