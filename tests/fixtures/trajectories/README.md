# Representative trajectory fixture evidence

This directory contains source manifests, not publishable trajectory payloads.
The current campaign source is license- and sanitization-blocked, and the
repository-owned generator is not materialized. Neither fixture is publication
qualified.

## Manifest contract

`fixture-manifest.schema.json` documents
`trajectory-fixture-source-manifest-v1`. The stdlib-only executable validator is
`scripts/benchmark_trajectory_store.py`; it intentionally avoids a new runtime
or optional dependency. The validator rejects unsupported versions, missing or
unexpected fields, unknown semantic shapes, bad digests/counts, inconsistent
status/payload state, malformed JSON, non-object roots, and duplicate fixture or
source identities.

Supported source classes have distinct evidence shapes:

- `campaign_long` records schema identity, source-file digests, record counts,
  and total source bytes.
- `unrelated_agent` records the deterministic generator, generation mode,
  expected step count, and network/live-key requirements.

Coverage values are booleans or one of the two explicit Lane B/C unknown
markers in the schema. An absent, misspelled, or free-form replacement is not an
implicit unknown; it is a typed schema failure.

## Publication gate

`selected_source_only` and `generator_selected_not_materialized` always remain
blocked. A manifest may claim `sanitized_payload_ready` only with committed
payloads, a qualified license, and a complete publication qualification:

- versioned deterministic transform receipt with input/output SHA-256;
- privacy policy ID/version and dropped/rewritten logical field paths;
- zero-finding qualified receipts for secret-key, free-form secret-value, PII,
  portability, and artifact scans;
- a qualified versioned loss report;
- repository-relative payload inventory with byte counts and matching file
  digests; the transform output digest covers the sorted inventory.

The validator reads only declared files to stream their digest and size. It does
not parse semantic trajectory payloads, construct v2 records, or retain raw
campaign data.

## Portable evidence

Manifests and readiness output use fixture IDs and repository-relative logical
paths. Host-specific absolute paths, drive-qualified paths, file URIs,
home-expanded paths, repository-external references, and local host endpoints
are reported only as typed finding codes; inspected values are never echoed.
Secret scans likewise publish only typed receipt identities and finding counts,
never matched content.

## Contract readiness input

The benchmark gate accepts an optional pure-data receipt set with version
`trajectory-contract-qualification-receipts-v1`. Each receipt contains exactly:

- `contract_id`, `version`, `digest`, and `fixture_identity`;
- boolean `qualified`;
- optional `qualification_authority`.

Unknown, duplicate, invalid, unqualified, unestablished-version, and
version-mismatched receipts are distinct blockers. One valid receipt qualifies
only its exact contract ID; fixture presence never auto-qualifies a Lane B/C
contract. The repository intentionally carries no fabricated qualification
receipt.

## Stable readiness behavior

Normal execution exits 2. `--dry-run` exits 0 for preflight automation, but both
emit `status: schema_not_ready`, an empty `measurements` list, and an empty
`claims` list while trajectory v2 remains unfrozen. This fixture set does not
establish 05A readiness, storage selection, compression benefit, or a Lane A
ratchet result.
