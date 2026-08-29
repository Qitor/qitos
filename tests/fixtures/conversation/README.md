# Conversation semantic fixtures

`v2/semantic_fixtures.json` is an in-repository contract fixture envelope, not
evidence of independent Lane C or Lane D consumers. Its two test consumers are
explicit simulations in `tests/core/test_conversation.py`.

Envelope version `qitos.conversation.fixture.v2` records two Phase 1 semantics:

- partial tool results persist immediately in actual completion order, while
  declaration order is an explicit derived query;
- `continuation_redacted_diagnostic_projection` removes only opaque provider
  continuation payloads. It leaves metadata and all other values unchanged and
  therefore is not a privacy-safe or public export.

Readers must check `fixture_version` before interpreting a manifest. The v1
envelope described buffered, declaration-ordered commit and the overbroad
`safe_projection` name, so this suite rejects v1 with
`UnsupportedSchemaVersionError` rather than silently reinterpreting it. The
nested ExchangeLog payload remains `qitos.exchange_log.v1`; that schema already
preserves item order and partial batches, so no persistence rewrite is needed.
