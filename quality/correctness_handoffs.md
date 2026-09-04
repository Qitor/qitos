# Correctness finding handoffs

Generated from `quality/static_baseline.json` at W1 baseline
`fb75cd5902fedf50d5e67dd617e62cd981c3128f`. These findings are not hygiene debt. Lane A owns
the gate; the named semantic lane owns the reproducer and fix.

## Lane B / Task 02

- `qitos/recipes/lats/__init__.py:341:5` — `mypy:override` / `invalid-override`: Signature of "prepare" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/magentic_one/__init__.py:290:5` — `mypy:override` / `invalid-override`: Signature of "prepare" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/moa/__init__.py:249:5` — `mypy:override` / `invalid-override`: Signature of "prepare" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/reflexion/__init__.py:218:5` — `mypy:override` / `invalid-override`: Signature of "prepare" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/self_refine/__init__.py:184:5` — `mypy:override` / `invalid-override`: Signature of "prepare" incompatible with supertype "qitos.core.agent_module.AgentModule"

## Lane B / Tasks 02/04

- `qitos/kit/embedding/local_embedding.py:34:16` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "get_sentence_embedding_dimension"
- `qitos/kit/embedding/local_embedding.py:52:16` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "encode"
- `qitos/kit/embedding/local_embedding.py:56:22` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "encode"
- `qitos/kit/parser/json_parser.py:302:18` — `flake8:F821` / `undefined-name`: undefined name 'List'
- `qitos/kit/parser/json_parser.py:302:18` — `mypy:name-defined` / `undefined-name`: Name "List" is not defined

## Lane C / Task 03

- `qitos/recipes/desktop/osworld_starter.py:497:23` — `mypy:union-attr` / `unbound-resource`: Item "None" of "RunSpec | None" has no attribute "environment"
- `qitos/recipes/lats/__init__.py:348:5` — `mypy:override` / `invalid-override`: Signature of "reduce" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/lats/__init__.py:360:21` — `mypy:operator` / `explicit-runtime-error`: Unsupported operand types for + ("str" and "None")
- `qitos/recipes/magentic_one/__init__.py:300:5` — `mypy:override` / `invalid-override`: Signature of "reduce" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/magentic_one/__init__.py:312:21` — `mypy:operator` / `explicit-runtime-error`: Unsupported operand types for + ("str" and "None")
- `qitos/recipes/moa/__init__.py:265:5` — `mypy:override` / `invalid-override`: Signature of "reduce" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/moa/__init__.py:277:21` — `mypy:operator` / `explicit-runtime-error`: Unsupported operand types for + ("str" and "None")
- `qitos/recipes/reflexion/__init__.py:224:5` — `mypy:override` / `invalid-override`: Signature of "reduce" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/reflexion/__init__.py:236:21` — `mypy:operator` / `explicit-runtime-error`: Unsupported operand types for + ("str" and "None")
- `qitos/recipes/self_refine/__init__.py:194:5` — `mypy:override` / `invalid-override`: Signature of "reduce" incompatible with supertype "qitos.core.agent_module.AgentModule"
- `qitos/recipes/self_refine/__init__.py:206:21` — `mypy:operator` / `explicit-runtime-error`: Unsupported operand types for + ("str" and "None")

## Lane C / Tasks 03/09/10

- `qitos/kit/env/web/providers.py:181:22` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "new_page"
- `qitos/kit/env/web/providers.py:184:9` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "goto"
- `qitos/kit/patterns/debate.py:45:16` — `mypy:name-defined` / `undefined-name`: Name "Annotated" is not defined
- `qitos/kit/skill/injector.py:138:34` — `flake8:F821` / `undefined-name`: undefined name 'SkillRegistry'
- `qitos/kit/skill/injector.py:138:34` — `mypy:name-defined` / `undefined-name`: Name "SkillRegistry" is not defined
- `qitos/kit/skill/injector.py:164:34` — `flake8:F821` / `undefined-name`: undefined name 'SkillRegistry'
- `qitos/kit/skill/injector.py:164:34` — `mypy:name-defined` / `undefined-name`: Name "SkillRegistry" is not defined
- `qitos/kit/tool/cron/scheduler.py:156:17` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "start"
- `qitos/kit/tool/cron/scheduler.py:172:13` — `mypy:attr-defined` / `unbound-resource`: "None" has no attribute "add_job"

## Lane D / Tasks 05/10

- `qitos/benchmark/tau_bench/port/envs/airline/tools/send_certificate.py:9:5` — `mypy:return` / `explicit-runtime-error`; vendored: Missing return statement
