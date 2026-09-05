"""Anthropic SSE assembly; message_stop closes a fully stopped message."""
from __future__ import annotations

import json
from typing import Any, Iterator

from .base import ModelStreamChunk
from ._stream import close_owned, failure, protocol_failure


def stream_message(model: Any, payload: dict[str, Any]) -> Iterator[ModelStreamChunk]:
    import requests

    response = None
    blocks: dict[int, dict[str, Any]] = {}
    arguments: dict[int, str] = {}
    closed: set[int] = set()
    message: dict[str, Any] = {}
    usage: dict[str, Any] = {}
    reason = None
    stopped = False
    model._set_last_usage(None)
    try:
        response = requests.post(
            f"{model.base_url}/v1/messages",
            headers={"x-api-key": model.api_key, "anthropic-version": model.api_version,
                     "content-type": "application/json"},
            json={**payload, "stream": True}, timeout=model.timeout, stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            line = raw_line.decode() if isinstance(raw_line, bytes) else str(raw_line)
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            kind = event.get("type")
            if kind == "ping":
                continue
            if stopped or kind == "error":
                raise protocol_failure(model)
            index = event.get("index", 0)
            if kind == "message_start":
                message = dict(event["message"])
                usage.update(message.get("usage") or {})
            elif kind == "content_block_start":
                if index in blocks or reason is not None:
                    raise protocol_failure(model)
                blocks[index] = dict(event["content_block"])
            elif kind == "content_block_delta":
                if index not in blocks or index in closed or reason is not None:
                    raise protocol_failure(model)
                delta = event["delta"]
                if delta["type"] == "text_delta":
                    text = delta.get("text", "")
                    blocks[index]["text"] = blocks[index].get("text", "") + text
                    if text:
                        yield ModelStreamChunk(text=text)
                elif delta["type"] == "input_json_delta":
                    arguments[index] = arguments.get(index, "") + delta.get("partial_json", "")
                elif delta["type"] == "thinking_delta":
                    blocks[index]["thinking"] = blocks[index].get("thinking", "") + delta.get("thinking", "")
                elif delta["type"] == "signature_delta":
                    blocks[index]["signature"] = blocks[index].get("signature", "") + delta.get("signature", "")
            elif kind == "content_block_stop":
                if index not in blocks or index in closed:
                    raise protocol_failure(model)
                if index in arguments:
                    value = json.loads(arguments[index])
                    if not isinstance(value, dict):
                        raise protocol_failure(model)
                    blocks[index]["input"] = value
                closed.add(index)
            elif kind == "message_delta":
                new_reason = event.get("delta", {}).get("stop_reason")
                if reason is not None and new_reason not in {None, reason}:
                    raise protocol_failure(model)
                reason = new_reason or reason
                usage.update(event.get("usage") or {})
            elif kind == "message_stop":
                if reason is None or set(blocks) != closed:
                    raise protocol_failure(model)
                stopped = True
        if not stopped:
            raise protocol_failure(model)
        message.update(content=[blocks[i] for i in sorted(blocks)], stop_reason=reason)
        if usage:
            message["usage"] = usage
        calls = [{"id": block.get("id"), "type": "function", "function": {
            "name": block.get("name"), "arguments": json.dumps(block.get("input")),
        }} for block in message["content"] if block.get("type") == "tool_use"]
        from ._stream import validate_calls

        validate_calls(model, calls, str(reason))
        known_usage = model._usage_from_response(message)
        model._set_last_usage(known_usage)
        yield ModelStreamChunk(text="", done=True, usage=known_usage, tool_calls=calls or None,
                               event_metadata={"finish_reason": reason, "response": message})
    except Exception as exc:
        raise failure(model, exc) from None
    finally:
        close_owned(response)
