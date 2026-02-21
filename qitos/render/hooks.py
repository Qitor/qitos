"""Render hooks built on top of the Engine hook system."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from ..core.action import Action
from ..engine.hooks import EngineHook, HookContext
from .cli_render import RichRender
from .events import RenderEvent

if TYPE_CHECKING:
    from ..engine.engine import Engine, EngineResult


class RenderHook(EngineHook):
    """Alias for render-specific hook implementations."""

_CLAUDE_THEME_PRESETS: Dict[str, Dict[str, Any]] = {
    "research": {
        "spinner": "dots",
        "banner_style": "bright_cyan",
        "status_style": "bold cyan",
        "icons": {
            "plan": "◆",
            "thinking": "◈",
            "action": "▶",
            "observation": "◉",
            "memory": "▣",
            "critic": "✦",
            "state": "◍",
            "error": "✖",
            "lifecycle": "●",
        },
        "styles": {
            "plan": "cyan",
            "thinking": "magenta",
            "action": "yellow",
            "observation": "green",
            "memory": "bright_blue",
            "critic": "bright_magenta",
            "state": "blue",
            "error": "red",
            "lifecycle": "bright_black",
        },
    },
    "minimal": {
        "spinner": "line",
        "banner_style": "white",
        "status_style": "bold white",
        "icons": {
            "plan": "P",
            "thinking": "T",
            "action": "A",
            "observation": "O",
            "memory": "M",
            "critic": "C",
            "state": "S",
            "error": "E",
            "lifecycle": "L",
        },
        "styles": {
            "plan": "white",
            "thinking": "white",
            "action": "white",
            "observation": "white",
            "memory": "white",
            "critic": "white",
            "state": "white",
            "error": "red",
            "lifecycle": "bright_black",
        },
    },
    "neon": {
        "spinner": "bouncingBall",
        "banner_style": "bold bright_green",
        "status_style": "bold bright_green",
        "icons": {
            "plan": "⬢",
            "thinking": "⚡",
            "action": "➤",
            "observation": "◎",
            "memory": "⬡",
            "critic": "✶",
            "state": "◌",
            "error": "⨯",
            "lifecycle": "●",
        },
        "styles": {
            "plan": "bright_cyan",
            "thinking": "bright_magenta",
            "action": "bright_yellow",
            "observation": "bright_green",
            "memory": "bright_blue",
            "critic": "bright_magenta",
            "state": "bright_cyan",
            "error": "bright_red",
            "lifecycle": "bright_black",
        },
    },
}


class RenderStreamHook(RenderHook):
    """Emit normalized render events for terminal and frontend consumers."""

    def __init__(self, output_jsonl: Optional[str] = None):
        self.events: List[RenderEvent] = []
        self.output_jsonl = output_jsonl
        self._path = Path(output_jsonl) if output_jsonl else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def on_run_start(self, task: str, state: Any, engine: "Engine") -> None:
        self._emit("lifecycle", "run_start", step_id=0, payload={"task": task, "max_steps": engine.budget.max_steps})

    def on_before_step(self, ctx: HookContext, engine: "Engine") -> None:
        self._emit("lifecycle", "step_start", step_id=ctx.step_id, payload={"phase": ctx.phase.value})

    def on_after_observe(self, ctx: HookContext, engine: "Engine") -> None:
        observation = ctx.observation
        self._emit("observation", "observation", step_id=ctx.step_id, payload={"observation": observation})
        if isinstance(ctx.env_view, dict):
            mem = ctx.env_view.get("memory")
            if isinstance(mem, dict):
                self._emit("memory", "memory_context", step_id=ctx.step_id, payload=mem)
        if isinstance(observation, dict) and "plan_steps" in observation:
            self._emit(
                "plan",
                "plan",
                step_id=ctx.step_id,
                payload={"plan_steps": observation.get("plan_steps"), "plan_cursor": observation.get("plan_cursor")},
            )

    def on_after_decide(self, ctx: HookContext, engine: "Engine") -> None:
        decision = ctx.decision
        if decision is None:
            return
        payload = {
            "mode": getattr(decision, "mode", None),
            "rationale": getattr(decision, "rationale", None),
            "actions": list(getattr(decision, "actions", []) or []),
            "final_answer": getattr(decision, "final_answer", None),
        }
        self._emit("thinking", "decision", step_id=ctx.step_id, payload=payload)
        if payload["actions"]:
            self._emit("action", "planned_actions", step_id=ctx.step_id, payload={"actions": payload["actions"]})

    def on_after_act(self, ctx: HookContext, engine: "Engine") -> None:
        if ctx.record is not None and ctx.record.tool_invocations:
            self._emit("action", "tool_invocations", step_id=ctx.step_id, payload={"tool_invocations": ctx.record.tool_invocations})
        if ctx.action_results:
            self._emit("observation", "action_results", step_id=ctx.step_id, payload={"action_results": ctx.action_results})

    def on_after_critic(self, ctx: HookContext, engine: "Engine") -> None:
        self._emit("critic", "critic", step_id=ctx.step_id, payload=ctx.payload or {})

    def on_after_reduce(self, ctx: HookContext, engine: "Engine") -> None:
        self._emit("state", "state_diff", step_id=ctx.step_id, payload=ctx.payload or {})

    def on_after_check_stop(self, ctx: HookContext, engine: "Engine") -> None:
        self._emit(
            "lifecycle",
            "check_stop",
            step_id=ctx.step_id,
            payload={"result": (ctx.payload or {}).get("result"), "stop_reason": ctx.stop_reason},
        )

    def on_recover(self, ctx: HookContext, engine: "Engine") -> None:
        self._emit("error", "recover", step_id=ctx.step_id, payload={"phase": ctx.phase.value, "error": str(ctx.error)})

    def on_after_step(self, ctx: HookContext, engine: "Engine") -> None:
        self._emit("lifecycle", "step_end", step_id=ctx.step_id, payload={"stop_reason": ctx.stop_reason})

    def on_run_end(self, result: "EngineResult", engine: "Engine") -> None:
        self._emit(
            "lifecycle",
            "done",
            step_id=max(0, result.step_count - 1),
            payload={"stop_reason": result.state.stop_reason, "final_result": result.state.final_result, "steps": result.step_count},
        )

    def on_event(self, event, state, record, engine) -> None:
        # Promote key model I/O events to first-class render nodes.
        if event.phase.value.lower() == "decide" and isinstance(event.payload, dict):
            stage = str(event.payload.get("stage", ""))
            if stage == "model_input":
                self._emit(
                    "thinking",
                    "model_input",
                    step_id=event.step_id,
                    payload={
                        "prepared": event.payload.get("prepared"),
                        "history_message_count": event.payload.get("history_message_count"),
                        "messages": event.payload.get("messages"),
                    },
                )
            elif stage == "model_output":
                self._emit(
                    "thinking",
                    "model_output",
                    step_id=event.step_id,
                    payload={"raw_output": event.payload.get("raw_output")},
                )
        self._emit(
            "engine_event",
            event.phase.value.lower(),
            step_id=event.step_id,
            payload={"ok": event.ok, "payload": event.payload, "error": event.error},
        )

    def _emit(self, channel: str, node: str, step_id: int, payload: Optional[Dict[str, Any]] = None) -> None:
        evt = RenderEvent(channel=channel, node=node, step_id=step_id, payload=payload or {})
        self.events.append(evt)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evt.to_dict(), ensure_ascii=False))
                f.write("\n")
        self.on_render_event(evt)

    def on_render_event(self, event: RenderEvent) -> None:
        """Override in subclasses for side effects (console/UI streaming)."""
        return None


class ClaudeStyleHook(RenderStreamHook):
    """Claude-code style readable terminal output with full intermediate nodes."""

    def __init__(
        self,
        output_jsonl: Optional[str] = None,
        max_preview_chars: int = 800,
        theme: str = "research",
    ):
        super().__init__(output_jsonl=output_jsonl)
        self.console = Console()
        self.max_preview_chars = max_preview_chars
        self._last_step: Optional[int] = None
        self._status: Any = None
        chosen = _CLAUDE_THEME_PRESETS.get(theme, _CLAUDE_THEME_PRESETS["research"])
        self.theme_name = theme if theme in _CLAUDE_THEME_PRESETS else "research"
        self._icons: Dict[str, str] = dict(chosen["icons"])
        self._styles: Dict[str, str] = dict(chosen["styles"])
        self._spinner: str = str(chosen["spinner"])
        self._banner_style: str = str(chosen["banner_style"])
        self._status_style: str = str(chosen["status_style"])

    def on_run_start(self, task: str, state: Any, engine: "Engine") -> None:
        super().on_run_start(task, state, engine)
        self._start_status("YOGA runtime is warming up")

    def on_before_observe(self, ctx: HookContext, engine: "Engine") -> None:
        self._update_status(f"Step {ctx.step_id}: observing environment")

    def on_before_decide(self, ctx: HookContext, engine: "Engine") -> None:
        self._update_status(f"Step {ctx.step_id}: thinking with model")

    def on_before_act(self, ctx: HookContext, engine: "Engine") -> None:
        self._update_status(f"Step {ctx.step_id}: executing action")

    def on_before_critic(self, ctx: HookContext, engine: "Engine") -> None:
        self._update_status(f"Step {ctx.step_id}: running critic")

    def on_before_reduce(self, ctx: HookContext, engine: "Engine") -> None:
        self._update_status(f"Step {ctx.step_id}: reducing state")

    def on_before_check_stop(self, ctx: HookContext, engine: "Engine") -> None:
        self._update_status(f"Step {ctx.step_id}: checking stop criteria")

    def on_run_end(self, result: "EngineResult", engine: "Engine") -> None:
        self._stop_status()
        super().on_run_end(result, engine)

    def on_render_event(self, event: RenderEvent) -> None:
        if event.node == "run_start":
            self._print_banner()
            self.console.print(Rule("[bold]RUN[/bold]", style="bright_black"))
            self.console.print(f"[cyan]task:[/cyan] {event.payload.get('task')}")
            self.console.print(f"[dim]theme:[/dim] {self.theme_name}")
            return

        if event.node == "step_start":
            self._last_step = event.step_id
            self.console.print(Rule(f"[bold]STEP {event.step_id}[/bold]", style="bright_black"))
            return

        if event.channel in {"plan", "thinking", "action", "observation", "memory", "critic", "state"}:
            icon = self._icons.get(event.channel, "•")
            style = self._styles.get(event.channel, "bright_black")
            title = f"{icon} {event.channel}:{event.node}"
            self.console.print(Panel(self._rich_value(event.payload), title=title, border_style=style))
            return

        if event.node == "done":
            self.console.print(Rule("[bold]DONE[/bold]", style="green"))
            self.console.print(f"[green]stop_reason:[/green] {event.payload.get('stop_reason')}")
            self.console.print(f"[green]final_result:[/green] {self._preview(event.payload.get('final_result'))}")
            return

    def _rich_value(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            dumped = json.dumps(value, ensure_ascii=False, indent=2)
            if len(dumped) > self.max_preview_chars:
                dumped = dumped[: self.max_preview_chars] + "\n... [truncated]"
            return Syntax(dumped, "json", word_wrap=True)
        return self._preview(value)

    def _preview(self, value: Any) -> str:
        text = str(value)
        if len(text) > self.max_preview_chars:
            return text[: self.max_preview_chars] + "... [truncated]"
        return text

    def _print_banner(self) -> None:
        banner_lines = [
            " __   __   ___    ____    ___ ",
            " \\ \\ / /  / _ \\  / ___|  / _ \\",
            "  \\ V /  | | | | | |  _  | | | |",
            "   | |   | |_| | | |_| | | |_| |",
            "   |_|    \\___/   \\____|  \\___/ ",
        ]
        body = Text("\n".join(banner_lines), style=self._banner_style)
        subtitle = Text("Agent Runtime Visual Console", style="dim")
        self.console.print(Panel(Text.assemble(body, "\n", subtitle), title="YOGA", border_style=self._banner_style))

    def _start_status(self, text: str) -> None:
        if self._status is None:
            self._status = self.console.status(
                f"[{self._status_style}]{text}[/]",
                spinner=self._spinner,
            )
            self._status.start()
        else:
            self._status.update(f"[{self._status_style}]{text}[/]")

    def _update_status(self, text: str) -> None:
        if self._status is None:
            self._start_status(text)
            return
        self._status.update(f"[{self._status_style}]{text}[/]")

    def _stop_status(self) -> None:
        if self._status is None:
            return
        self._status.stop()
        self._status = None


class RichConsoleHook(RenderHook):
    """Legacy rich hook kept for compatibility."""

    def __init__(
        self,
        show_step_header: bool = True,
        show_thought: bool = True,
        show_action: bool = True,
        show_observation: bool = True,
        show_final_answer: bool = True,
    ):
        self.show_step_header = show_step_header
        self.show_thought = show_thought
        self.show_action = show_action
        self.show_observation = show_observation
        self.show_final_answer = show_final_answer
        self._tools_used: list[str] = []

    def on_step_end(self, record, state, engine) -> None:
        decision = record.decision
        if decision is not None and self.show_thought and getattr(decision, "rationale", None):
            RichRender.print_thought(str(decision.rationale), record.step_id)
        if decision is not None and self.show_action and getattr(decision, "actions", None):
            for action in decision.actions:
                obj = action if isinstance(action, Action) else Action.from_dict(action)
                self._tools_used.append(obj.name)
                RichRender.print_action(obj.name, obj.args, record.step_id)
        if self.show_observation and record.action_results:
            for obs in record.action_results:
                RichRender.print_observation(obs, record.step_id)

    def on_run_end(self, result: "EngineResult", engine: "Engine") -> None:
        if self.show_final_answer and result.state.final_result is not None:
            RichRender.print_final_answer(str(result.state.final_result), result.state.task)


class SimpleRichConsoleHook(RichConsoleHook):
    def __init__(self):
        super().__init__(show_step_header=False, show_thought=False, show_action=False, show_observation=False, show_final_answer=True)


class VerboseRichConsoleHook(RichConsoleHook):
    def __init__(self):
        super().__init__(show_step_header=True, show_thought=True, show_action=True, show_observation=True, show_final_answer=True)


__all__ = [
    "RenderHook",
    "RenderStreamHook",
    "ClaudeStyleHook",
    "RichConsoleHook",
    "SimpleRichConsoleHook",
    "VerboseRichConsoleHook",
]
