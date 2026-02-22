# Example Walkthroughs

## Goal

These pages explain **why each example is written the way it is**, mapping every `AgentModule` method to a specific agentic design principle.

If you only “run the script”, you will miss the core value of QitOS:

- stable kernel semantics (`AgentModule + Engine`)
- comparable behavior via explicit lifecycle phases
- reproducible evidence via trace + qita

## Pattern examples

- ReAct (text protocol): [ReAct Walkthrough](react.md)
- PlanAct (plan first, execute step-by-step): [PlanAct Walkthrough](planact.md)
- Reflexion (actor-critic with grounded critique): [Reflexion Walkthrough](reflexion.md)
- Tree-of-Thought (branch + search selection): [Tree-of-Thought Walkthrough](tot.md)

## Practical examples

- Coding agent (ReAct + self-reflection + memory.md): [Coding Walkthrough](real_coding.md)
- SWE agent (dynamic plan + branch selection): [SWE Walkthrough](real_swe.md)
- Computer-use web research agent (JSON decisions): [Computer-Use Walkthrough](real_computer_use.md)
- EPUB reader ToT agent (branching over evidence): [EPUB Reader Walkthrough](real_epub_reader.md)

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [examples/patterns/tot.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/tot.py)
- [examples/real/coding_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/coding_agent.py)
- [examples/real/swe_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/swe_agent.py)
- [examples/real/computer_use_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/computer_use_agent.py)
- [examples/real/epub_reader_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/epub_reader_agent.py)
