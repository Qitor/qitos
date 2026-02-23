# `qitos.render.hooks`

- Module Group: `qitos.render`
- Source: [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `ClaudeStyleHook`](#class-claudestylehook)
- [Class: `RenderHook`](#class-renderhook)
- [Class: `RenderStreamHook`](#class-renderstreamhook)
- [Class: `RichConsoleHook`](#class-richconsolehook)
- [Class: `SimpleRichConsoleHook`](#class-simplerichconsolehook)
- [Class: `VerboseRichConsoleHook`](#class-verboserichconsolehook)

## Classes

<a id="class-claudestylehook"></a>
???+ note "Class: `ClaudeStyleHook(self, output_jsonl: 'Optional[str]' = None, max_preview_chars: 'int' = 800, theme: 'str' = 'research')`"
    Content-first terminal output focused on task, thought, action, observation, memory.

<a id="class-renderhook"></a>
???+ note "Class: `RenderHook(self, /, *args, **kwargs)`"
    Alias for render-specific hook implementations.

<a id="class-renderstreamhook"></a>
???+ note "Class: `RenderStreamHook(self, output_jsonl: 'Optional[str]' = None)`"
    Emit normalized render events for terminal and frontend consumers.

<a id="class-richconsolehook"></a>
???+ note "Class: `RichConsoleHook(self, show_step_header: 'bool' = True, show_thought: 'bool' = True, show_action: 'bool' = True, show_observation: 'bool' = True, show_final_answer: 'bool' = True)`"
    Legacy rich hook kept for compatibility.

<a id="class-simplerichconsolehook"></a>
???+ note "Class: `SimpleRichConsoleHook(self)`"
    Legacy rich hook kept for compatibility.

<a id="class-verboserichconsolehook"></a>
???+ note "Class: `VerboseRichConsoleHook(self)`"
    Legacy rich hook kept for compatibility.

## Functions

- _None_

## Source Index

- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)