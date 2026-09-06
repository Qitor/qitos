# R1 installed combination

Build one wheel and install it in a fresh Python 3.12.7 virtual environment. Copy
`consumer.py` outside the repository, unset PYTHONPATH, and use that environment:

```sh
python -I consumer.py seed --root ./normal
python -I consumer.py first --root ./normal
python -I consumer.py restore --root ./normal
python -I consumer.py namespace --root ./normal
python -I consumer.py seed --root ./failure
python -I consumer.py failure --root ./failure
python -I consumer.py seed --root ./no-loss
python -I consumer.py no-loss --root ./no-loss
```

Each command is a separate process. Memdir initialization is explicit; subsequent
construction restores disk records. `agent.yaml` names the budget factory and
explicitly authorizes codec loss. This example uses built-in OpenAI-compatible
adapters with synthetic SDK responses, not live models. A real local scheduler
acknowledges handoff; the next process restores the destination. The first five
requests stream and restored requests use nonstream adapter calls. Assertions cover
raw log preservation, actual compactions and loss, protected data, unrelated work,
correct tool identity and deliberately inverted first-batch completion order,
cleanup failure and canonical journal exports. No source PYTHONPATH, test helper,
private Engine field, fabricated trajectory or copied execution loop is used.
