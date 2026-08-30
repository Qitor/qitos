# Stable session contract fixtures

This directory has no version-named subdirectory. Payloads carry their own
`schema_version`; the current writer emits schema `1`, and strict readers reject
unknown fields, wrong types, non-JSON values, non-finite numbers, unsupported
component schemas, and integrity mismatches.

- `identity-vocabulary.json` is the Lane A producer fixture. B/C/D import the
  identity types and relationship enum from `qitos.core.session`; copying the
  enum or inferring lineage from identifier text is invalid.
- `semantic-fixtures.json` names the required lifecycle, persistence, resolver,
  conflict, restore, and isolated-fork cases. Tests materialize each case through
  the current snapshot writer so fixture intent cannot drift from the codec.
- `restore-candidate.json` and `forked-session.json` are canonical full snapshot
  envelopes with verified SHA-256 integrity (added by the fixture writer tests).
- `qualification-evidence.json` binds producer commits and file digests for
  cross-lane consumers (added after final qualification).

All values are synthetic and portable. Fixtures contain no live object, secret,
credential, raw provider payload, or host-local path.
