# `qitos.benchmark.gaia`

- 模块分组: `qitos.benchmark`
- 源码: [qitos/benchmark/gaia.py](https://github.com/Qitor/qitos/blob/main/qitos/benchmark/gaia.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `GaiaAdapter`](#class-gaiaadapter)
- [Function: `load_gaia_tasks`](#function-load-gaia-tasks)

## Classes

<a id="class-gaiaadapter"></a>
???+ note "Class: `GaiaAdapter(self, dataset_name: 'str' = 'gaia-benchmark/GAIA', annotated_dataset_name: 'str' = 'smolagents/GAIA-annotated', local_dir: 'str' = 'data/gaia', config_name: 'str' = '2023_all', default_subset: 'Optional[str]' = None, task_prefix: 'str' = 'gaia', include_raw_record: 'bool' = True, default_max_steps: 'int' = 24, default_env_spec: 'EnvSpec' = <factory>) -> None`"
    Convert GAIA dataset rows to canonical QitOS Task objects.

## Functions

<a id="function-load-gaia-tasks"></a>
???+ note "Function: `load_gaia_tasks(split: 'str' = 'validation', subset: 'Optional[str]' = None, limit: 'Optional[int]' = None, cache_dir: 'Optional[str]' = None) -> 'list[Task]'`"
    Convenience loader: Hugging Face GAIA -> list[Task].

## Source Index

- [qitos/benchmark/gaia.py](https://github.com/Qitor/qitos/blob/main/qitos/benchmark/gaia.py)