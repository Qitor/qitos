# Issue #33 Native Text Action Intent Design

## Problem

When native tool calling is preferred, a non-empty model response without
native `tool_calls` is parsed first and then treated as a final answer if the
parser returns `Decision.wait`. That fallback is correct for ordinary natural
language conclusions, but it also overrides parser-error waits for malformed
structured action text. The Engine can therefore report `final` even though the
model intended to invoke a tool and no tool ran.

## Design

Keep `native_text_final` as the default for ordinary natural language. Before
using it, distinguish a parser failure that contains high-confidence structured
action intent. Detection stays private to the model runtime and recognizes
action-schema fields only in structured positions, such as labeled lines,
JSON-like keys, XML-like tags, or provider-native tool-call markers. Ambiguous
labels such as `Command:`, `Call:`, or `Tools:` require a corroborating schema
field, while the same keys inside a JSON object are high-confidence structured
intent. A lone prose label or an action word in a sentence is not sufficient.

The native text branch applies these rules in order:

1. Preserve parsed `act` and `final` decisions.
2. Preserve a successfully parsed, explicit JSON or XML `wait` decision.
3. Preserve a parser-error `wait` when the raw text looks like structured
   action intent, allowing the existing parser recovery path to run.
4. Keep the existing `native_text_final` fallback for all other parser waits,
   including parser-specific heuristic waits that are not parse errors.

The change does not alter parser contracts, provider adapters, family presets,
tool execution, stop criteria, or trace schemas.

## Observability

The parser path already records the raw model response, parser attempts, and
structured diagnostics. Returning the parser-error wait leaves
`decision_source="parser"` intact instead of overwriting it with
`native_text_final`. A DECIDE event records why the final fallback was rejected.

## Validation

- A malformed labeled action must remain `wait` with `parser_error=True`.
- A malformed JSON-like action must remain on parser recovery.
- Truncated MiniMax and tool-use XML actions must remain on parser recovery.
- Ordinary natural language must still become `native_text_final`.
- Ambiguous prose labels and parser-specific heuristic waits must retain the
  existing final fallback.
- Explicit JSON and XML wait signals must remain parser decisions.
- Valid parsed actions, valid final answers, and native `tool_calls` must remain
  unchanged.
- Existing targeted and full test suites, stable-surface lint, and type checks
  must pass.
