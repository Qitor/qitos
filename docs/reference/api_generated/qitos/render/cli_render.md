# `qitos.render.cli_render`

- Module Group: `qitos.render`
- Source: [qitos/render/cli_render.py](https://github.com/Qitor/qitos/blob/main/qitos/render/cli_render.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `PromptPreviewPanel`](#class-promptpreviewpanel)
- [Class: `RichRender`](#class-richrender)
- [Function: `print_action`](#function-print-action)
- [Function: `print_error`](#function-print-error)
- [Function: `print_final_answer`](#function-print-final-answer)
- [Function: `print_llm_input`](#function-print-llm-input)
- [Function: `print_observation`](#function-print-observation)
- [Function: `print_step_header`](#function-print-step-header)
- [Function: `print_thought`](#function-print-thought)

## Classes

<a id="class-promptpreviewpanel"></a>
???+ note "Class: `PromptPreviewPanel(self, content, **kwargs)`"
    Custom panel for displaying system prompt preview.

<a id="class-richrender"></a>
???+ note "Class: `RichRender(self, /, *args, **kwargs)`"
    Unified Rich rendering component for QitOS CLI.

## Functions

<a id="function-print-action"></a>
???+ note "Function: `print_action(tool_name: str, args: Dict[str, Any], step: Optional[int] = None) -> None`"
    Convenience function for RichRender.print_action

<a id="function-print-error"></a>
???+ note "Function: `print_error(msg: str, exception: Optional[Exception] = None) -> None`"
    Convenience function for RichRender.print_error

<a id="function-print-final-answer"></a>
???+ note "Function: `print_final_answer(answer: str, task: Optional[str] = None) -> None`"
    Convenience function for RichRender.print_final_answer

<a id="function-print-llm-input"></a>
???+ note "Function: `print_llm_input(messages: List[Dict[str, Any]], step: Optional[int] = None) -> None`"
    Convenience function for RichRender.print_llm_input

<a id="function-print-observation"></a>
???+ note "Function: `print_observation(content: Any, step: Optional[int] = None) -> None`"
    Convenience function for RichRender.print_observation

<a id="function-print-step-header"></a>
???+ note "Function: `print_step_header(step: int, total_steps: Optional[int] = None) -> None`"
    Convenience function for RichRender.print_step_header

<a id="function-print-thought"></a>
???+ note "Function: `print_thought(text: str, step: Optional[int] = None) -> None`"
    Convenience function for RichRender.print_thought

## Source Index

- [qitos/render/cli_render.py](https://github.com/Qitor/qitos/blob/main/qitos/render/cli_render.py)