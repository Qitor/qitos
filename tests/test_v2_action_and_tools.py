from dataclasses import dataclass
from typing import Any, Dict, Optional

from qitos.core.action import Action, ActionStatus
from qitos.core.skill import ToolRegistry as LegacyToolRegistry, skill
from qitos.core.tool import ToolPermission, tool
from qitos import Decision, Policy, Runtime, RuntimeBudget, ToolRegistry
from qitos.engine.action_executor import ActionExecutor


class TestActionExecutor:
    def test_action_executor_success(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)

        executor = ActionExecutor(registry)
        result = executor.execute([Action(name="add", args={"a": 1, "b": 2})])

        assert len(result) == 1
        assert result[0].status == ActionStatus.SUCCESS
        assert result[0].output == 3

    def test_action_executor_retry(self):
        registry = ToolRegistry()
        call_count = {"n": 0}

        @tool(name="flaky")
        def flaky() -> str:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("temporary")
            return "ok"

        registry.register(flaky)
        executor = ActionExecutor(registry)

        result = executor.execute([Action(name="flaky", max_retries=1)])

        assert result[0].status == ActionStatus.SUCCESS
        assert result[0].attempts == 2
        assert result[0].output == "ok"


class TestToolRegistry:
    def test_bound_method_registration_keeps_self(self):
        class Counter:
            def __init__(self):
                self.base = 40

            @tool(name="inc")
            def inc(self, delta: int) -> int:
                return self.base + delta

        registry = ToolRegistry()
        registry.include(Counter())

        assert registry.call("inc", delta=2) == 42

    def test_permissions_metadata(self):
        registry = ToolRegistry()

        @tool(name="read", permissions=ToolPermission(filesystem_read=True))
        def read_file(path: str) -> str:
            return path

        registry.register(read_file)
        specs = registry.get_all_specs()
        assert specs[0]["permissions"]["filesystem_read"] is True


class TestLegacySkillBindingFix:
    def test_legacy_skill_on_method_works(self):
        class LegacyCounter:
            def __init__(self):
                self.base = 41

            @skill(name="legacy_inc", domain="test")
            def legacy_inc(self, delta: int) -> int:
                return self.base + delta

        registry = LegacyToolRegistry()
        registry.include(LegacyCounter())

        assert registry.call("legacy_inc", delta=1) == 42


@dataclass
class _State:
    task: str
    current_step: int = 0
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None


class _SingleStepPolicy(Policy[_State, Dict[str, Any], Action]):
    def propose(self, state: _State, obs: Dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name="math.add", args={"a": 40, "b": 2})])
        return Decision.final(str(state.final_result or ""))

    def update(self, state: _State, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> _State:
        if results:
            state.final_result = str(results[0])
        return state


class TestToolSetLifecycle:
    def test_toolset_setup_teardown(self):
        events: list[str] = []

        class MathToolSet:
            name = "math"
            version = "1.0"

            def setup(self, context: dict[str, Any]) -> None:
                events.append("setup")

            def teardown(self, context: dict[str, Any]) -> None:
                events.append("teardown")

            @tool(name="add")
            def add(self, a: int, b: int) -> int:
                return a + b

            def tools(self) -> list[Any]:
                return [self.add]

        registry = ToolRegistry()
        registry.register_toolset(MathToolSet())

        runtime = Runtime(policy=_SingleStepPolicy(), toolkit=registry, budget=RuntimeBudget(max_steps=2))
        result = runtime.run(_State(task="sum"))

        assert result.state.final_result == "42"
        assert events == ["setup", "teardown"]
