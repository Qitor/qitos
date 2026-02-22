# `qitos.kit.planning.agent_blocks`

- 模块分组: `qitos.kit`
- 源码: [qitos/kit/planning/agent_blocks.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/agent_blocks.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `LLMDecisionBlock`](#class-llmdecisionblock)
- [Class: `ToolAwareMessageBuilder`](#class-toolawaremessagebuilder)

## Classes

<a id="class-llmdecisionblock"></a>
???+ note "Class: `LLMDecisionBlock(self, llm: 'Any', parser: 'Parser[Any]', fallback_to_final: 'bool' = True) -> None`"
    Call LLM and parse into Decision with safe fallback behavior.

<a id="class-toolawaremessagebuilder"></a>
???+ note "Class: `ToolAwareMessageBuilder(self, system_template: 'str', max_history_items: 'int' = 8) -> None`"
    Build stable LLM messages with tool schema and scratchpad context.

## Functions

- _无_

## Source Index

- [qitos/kit/planning/agent_blocks.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/agent_blocks.py)