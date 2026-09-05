# Configured text memory and closed-exchange compaction

Build the reviewed source with Python 3.12.7 (`python -m build`). Install its
wheel into a new venv, then copy `consumer.py` and `agent.yaml` into a directory
outside the repository. From that directory, using the installed interpreter:

```bash
python -I consumer.py seed --root ./evidence
python -I consumer.py run --root ./evidence
```

The seed process explicitly initializes `project` and `other` resources and
writes one text record. The run process restores the existing roots, resolves
`project_memory` and `closed_window` through `extensions`, and executes ten
real Engine requests with a deterministic provider. It checks actual encoded
memory visibility, at least two budget compactions, the recent-two window,
selected chunk visibility and recorded request identity. An additional actual
request through a composition bound to the other namespace verifies absence of
the remembered value.
`report.json` identifies the installed package and observed counts. This is
mechanism evidence, not live model capability evidence.

The YAML loader accepts `memory.sources`, `compaction.provider`,
`context.budget_policy: budget` and `context.allow_codec_loss: true`.
The caller binds the named budget through the existing extensions factory;
unknown names and non-boolean loss values fail before model dispatch.
The compactor
itself never enables codec loss. The selected 100,000-character input budget
also accommodates ConfiguredAgent's repeated recent-observation projection.
It is an example policy, not a framework default or automatic budget increase.

`MemorySourceAdapter` borrows the memory. Its namespace is a logical label;
the factory binds that label to a root, not to unrestricted directory access.
Do not pass `create=True` during restore. Missing roots raise
`MemoryResourceError`. Cache reset/eviction and adapter close do not delete
persisted records. Memdir supports text records; arbitrary Python/JSON metadata
is not promised to round-trip. MarkdownFileMemory uses this same adapter only
within its current instance; constructing it over an existing log does not
reload the records.

The window policy omits the oldest eligible closed exchanges without a summary.
It changes only the RequestView, not ExchangeLog persistence. Required content,
required artifacts, incomplete exchanges and pending steering stay protected;
opaque continuation references conservatively protect the entire dependency
history. Failure to fit protected content is typed. A content revision is never
used as a permanent suppression cache, so recall reappears after restore or
an earlier omission. Legacy CompactHistory remains a separate compatibility
path. Model summaries, Markdown durable reading, cross-Agent memory policy and
original-Agent migration experiments remain outside this example.
