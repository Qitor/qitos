# `qitos.kit.parser.func_parser`

- 模块分组: `qitos.kit`
- 源码: [qitos/kit/parser/func_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/func_parser.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Function: `extract_function_calls`](#function-extract-function-calls)
- [Function: `parse_first_action_invocation`](#function-parse-first-action-invocation)
- [Function: `parse_kwargs_loose`](#function-parse-kwargs-loose)
- [Function: `split_args_robust`](#function-split-args-robust)

## Classes

- _无_

## Functions

<a id="function-extract-function-calls"></a>
???+ note "Function: `extract_function_calls(code_str: 'str') -> 'Iterator[Tuple[str, str, bool]]'`"
    Extract function calls from text using balanced-parentheses scanning.

<a id="function-parse-first-action-invocation"></a>
???+ note "Function: `parse_first_action_invocation(text: 'str') -> 'Optional[Dict[str, Any]]'`"
    Parse first action function invocation from an LLM output blob.

<a id="function-parse-kwargs-loose"></a>
???+ note "Function: `parse_kwargs_loose(arg_str: 'str') -> 'Dict[str, Any]'`"
    Best-effort kwargs parser for function arguments.

<a id="function-split-args-robust"></a>
???+ note "Function: `split_args_robust(arg_str: 'str') -> 'List[str]'`"
    Split function args by top-level commas while respecting nested structures.

## Source Index

- [qitos/kit/parser/func_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/func_parser.py)