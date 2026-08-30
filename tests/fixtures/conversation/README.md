# Conversation semantic fixtures

`request_contracts.json` is the current stable-path S1 Lane B fixture. It
contains versioned `RequestView`, `CodecReport`, and conversation-component
samples plus the complete semantic case manifest. Its adjacent evidence remains
`waiting_on_lane_a` until the reviewed Lane A snapshot envelope is consumed and
the producer commit/digests are final.

The `v3/` directory is the qualified G1 compatibility envelope. No new S1
fixture is added under that version directory; its bytes and evidence path stay
unchanged until Lane D and the integration owner migrate the existing receipt.

`v3/semantic_fixtures.json` is the G1 producer fixture envelope. Its execution
and persistence consumers are explicit in `tests/core/test_conversation.py`,
including direct consumption of Lane C's committed canonical result fixture.

Envelope version `qitos.conversation.fixture.v3` records the converged G1 semantics:

- partial tool results persist immediately in actual completion order, while
  declaration order is an explicit derived query;
- `continuation_redacted_diagnostic_projection` removes only opaque provider
  continuation payloads. It leaves metadata and all other values unchanged and
  therefore is not a privacy-safe or public export.

Readers must check `fixture_version` before interpreting a manifest. The v1
envelope described buffered, declaration-ordered commit and the overbroad
`safe_projection` name, so this suite rejects v1 with
`UnsupportedSchemaVersionError` rather than silently reinterpreting it. The
nested ExchangeLog payload is `qitos.exchange_log.v2`; it delegates every
tool outcome to canonical `qitos.tool_result/v1` and rejects unknown or malformed
fields with `ConversationValidationError` while preserving item order and
partial batches.
