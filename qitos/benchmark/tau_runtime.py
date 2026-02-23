"""Self-contained Tau-Bench runtime used by QitOS benchmark integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import import_module
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from qitos.benchmark.tau_port.types import Action, RESPOND_ACTION_FIELD_NAME, RESPOND_ACTION_NAME, Task

ToHashable = Union[str, int, float, Dict[str, "ToHashable"], List["ToHashable"], Set["ToHashable"]]
Hashable = Union[str, int, float, Tuple["Hashable"], Tuple[Tuple[str, "Hashable"]]]


def _to_hashable(item: ToHashable) -> Hashable:
    if isinstance(item, dict):
        return tuple((key, _to_hashable(value)) for key, value in sorted(item.items()))
    if isinstance(item, list):
        return tuple(_to_hashable(element) for element in item)
    if isinstance(item, set):
        return tuple(sorted(_to_hashable(element) for element in item))
    return item


def _consistent_hash(value: Hashable) -> str:
    return sha256(str(value).encode("utf-8")).hexdigest()


@dataclass
class TauEnvInfo:
    task: Dict[str, Any]
    source: Optional[str] = None
    reward_info: Optional[Dict[str, Any]] = None

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TauEnvResponse:
    observation: str
    reward: float
    done: bool
    info: TauEnvInfo


@dataclass
class TauEnvResetResponse:
    observation: str
    info: TauEnvInfo


class TauRuntimeEnv:
    """A minimal Tau runtime (tool execution + reward) without external tau_bench dependency."""

    def __init__(
        self,
        env_name: str,
        task_split: str = "test",
        task_index: Optional[int] = None,
    ):
        env_name = str(env_name)
        task_split = str(task_split)
        self.env_name = env_name
        self.task_split = task_split

        self._load_data, self.tool_classes, self.tasks, self.wiki, self.rules, self.terminate_tools = self._load_assets(
            env_name, task_split
        )

        self.tools_map = {tool.get_info()["function"]["name"]: tool for tool in self.tool_classes}
        self.tools_info = [tool.get_info() for tool in self.tool_classes]

        self.task_index = int(task_index or 0)
        self.data = self._load_data()
        self.task = self.tasks[self.task_index]
        self.actions: List[Action] = []

    def reset(self, task_index: Optional[int] = None) -> TauEnvResetResponse:
        if task_index is not None:
            self.task_index = int(task_index)
        self.data = self._load_data()
        self.task = self.tasks[self.task_index]
        self.actions = []
        return TauEnvResetResponse(
            observation=str(self.task.instruction),
            info=TauEnvInfo(task=self.task.model_dump(), source="instruction"),
        )

    def step(self, action: Action) -> TauEnvResponse:
        self.actions.append(action)
        info = TauEnvInfo(task=self.task.model_dump(), source=action.name)
        reward = 0.0
        done = False

        if action.name in self.tools_map:
            try:
                observation = self.tools_map[action.name].invoke(data=self.data, **action.kwargs)
                observation = str(observation)
            except Exception as exc:
                observation = f"Error: {exc}"
            if action.name in self.terminate_tools:
                done = True
        elif action.name == RESPOND_ACTION_NAME:
            observation = str(action.kwargs.get(RESPOND_ACTION_FIELD_NAME, ""))
            done = True
        else:
            observation = f"Unknown action {action.name}"

        if done:
            reward_info = self.calculate_reward()
            reward = float(reward_info.get("reward", 0.0))
            info.reward_info = reward_info

        return TauEnvResponse(observation=observation, reward=reward, done=done, info=info)

    def get_data_hash(self) -> str:
        return _consistent_hash(_to_hashable(self.data))

    def calculate_reward(self) -> Dict[str, Any]:
        data_hash = self.get_data_hash()

        # Compute expected end-state hash by replaying GT actions on fresh state.
        gt_data = self._load_data()
        gt_tools = self.tools_map
        for action in self.task.actions:
            if action.name in self.terminate_tools:
                continue
            tool = gt_tools.get(action.name)
            if tool is None:
                continue
            try:
                tool.invoke(data=gt_data, **action.kwargs)
            except Exception:
                pass
        gt_data_hash = _consistent_hash(_to_hashable(gt_data))

        reward = 1.0 if data_hash == gt_data_hash else 0.0
        details: Dict[str, Any] = {
            "r_actions": data_hash == gt_data_hash,
            "gt_data_hash": gt_data_hash,
            "data_hash": data_hash,
        }

        if self.task.outputs:
            outputs: Dict[str, bool] = {}
            ok = True
            for expected in self.task.outputs:
                found = any(
                    a.name == RESPOND_ACTION_NAME and str(expected).lower() in str(a.kwargs.get(RESPOND_ACTION_FIELD_NAME, "")).lower().replace(",", "")
                    for a in self.actions
                )
                outputs[str(expected)] = bool(found)
                if not found:
                    ok = False
            details["r_outputs"] = 1.0 if ok else 0.0
            details["outputs"] = outputs
            if not ok:
                reward = 0.0

        return {
            "reward": reward,
            "info": details,
            "actions": [a.model_dump() for a in self.task.actions if a.name != RESPOND_ACTION_NAME],
        }

    def _load_assets(self, env_name: str, split: str):
        if env_name == "retail":
            data_mod = import_module("qitos.benchmark.tau_port.envs.retail.data")
            tools_mod = import_module("qitos.benchmark.tau_port.envs.retail.tools")
            wiki_mod = import_module("qitos.benchmark.tau_port.envs.retail.wiki")
            rules_mod = import_module("qitos.benchmark.tau_port.envs.retail.rules")
            if split == "test":
                tasks_mod = import_module("qitos.benchmark.tau_port.envs.retail.tasks_test")
                tasks_raw = getattr(tasks_mod, "TASKS_TEST")
            elif split == "train":
                tasks_mod = import_module("qitos.benchmark.tau_port.envs.retail.tasks_train")
                tasks_raw = getattr(tasks_mod, "TASKS_TRAIN")
            elif split == "dev":
                tasks_mod = import_module("qitos.benchmark.tau_port.envs.retail.tasks_dev")
                tasks_raw = getattr(tasks_mod, "TASKS_DEV")
            else:
                raise ValueError(f"Unsupported retail split: {split}")
            terminate_tools = ["transfer_to_human_agents"]
        elif env_name == "airline":
            data_mod = import_module("qitos.benchmark.tau_port.envs.airline.data")
            tools_mod = import_module("qitos.benchmark.tau_port.envs.airline.tools")
            wiki_mod = import_module("qitos.benchmark.tau_port.envs.airline.wiki")
            rules_mod = import_module("qitos.benchmark.tau_port.envs.airline.rules")
            if split == "test":
                tasks_mod = import_module("qitos.benchmark.tau_port.envs.airline.tasks_test")
                tasks_raw = getattr(tasks_mod, "TASKS")
            else:
                raise ValueError(f"Unsupported airline split: {split}")
            terminate_tools = ["transfer_to_human_agents"]
        else:
            raise ValueError(f"Unsupported Tau env: {env_name}")

        tasks = [self._normalize_task(t) for t in list(tasks_raw)]
        return data_mod.load_data, list(tools_mod.ALL_TOOLS), tasks, str(wiki_mod.WIKI), list(rules_mod.RULES), terminate_tools

    def _normalize_task(self, t: Any) -> Task:
        if isinstance(t, Task):
            return t
        payload = t.model_dump() if hasattr(t, "model_dump") else dict(t)
        actions = [
            Action(name=str(a.get("name", "")), kwargs=dict(a.get("kwargs") or a.get("arguments") or {}))
            for a in list(payload.get("actions", []) or [])
        ]
        return Task(
            user_id=str(payload.get("user_id", "")),
            actions=actions,
            instruction=str(payload.get("instruction", "")),
            outputs=[str(x) for x in list(payload.get("outputs", []) or [])],
        )


def get_tau_runtime_env(env_name: str, task_split: str, task_index: Optional[int] = None) -> TauRuntimeEnv:
    return TauRuntimeEnv(env_name=env_name, task_split=task_split, task_index=task_index)
