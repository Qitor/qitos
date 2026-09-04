# QitOS documentation

The bilingual Mintlify source is configured in docs.json. The beginner order is
installation → project → canonical configuration → Session → inspection → recovery.
See CONTRIBUTING.md and AGENTS.md for paired content and executable lesson rules.

Use a task-isolated tools directory (no global upgrades):

```bash
mkdir -p ../qitos-doc-tools
npm install --prefix ../qitos-doc-tools mint@4.2.873 @mdx-js/mdx@3.1.1
python scripts/validate_docs.py
cd docs
../../qitos-doc-tools/node_modules/.bin/mint validate --telemetry false
../../qitos-doc-tools/node_modules/.bin/mint broken-links --telemetry false
../../qitos-doc-tools/node_modules/.bin/mint dev --port 3333 --telemetry false
```

Run Python commands from the repository root. The pinned versions are verified
in the promotion ledger; change them deliberately after verification.
Inspect both languages for introduction, Quickstart, Session, multi-agent,
sandbox, qita and configuration, including a narrow mobile viewport.
This is local preview only; this task does not deploy the documentation site.

## Self-contained teaching pages

Edit executable sources under `examples/tutorials/notes`, then synchronize with
`python scripts/sync_tutorial_docs.py`. Every chapter includes all dependencies
inline; source links are optional. API imports and source signatures are declared
in `docs/api-contracts.json`; run `python scripts/sync_api_reference.py` in an
environment with the matching QitOS installation. CI uses both scripts with
`--check` and executes page-extracted files through `tests/test_docs_page_execution.py`.
Maintain EN/zh prose together; do not translate executable identifiers or defaults.
