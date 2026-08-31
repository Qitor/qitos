# Trajectory readiness fixtures

This stable directory contains Lane D readiness inputs, not producer schemas or
Trajectory payloads. `contract-qualification-receipts.json` now contains 21
independent bindings: two explicitly historical G1 compatibility receipts,
two G2-R2 current ToolResult/ExchangeLog writer receipts, and all 17 G2 A/B/C
contract requirements. These receipts qualify contract bytes only; they do
not establish runtime or Trajectory readiness.

`scenarios.json` is a schema-checked inventory of required readiness behaviors.
Scenario availability labels are test instructions. Adversarial tests construct
a temporary Git repository, commit synthetic fixture/evidence bytes, and
compute their exact identities at runtime. Repository receipts use only the
reviewed producer versions, commits, paths, digests, authority, evidence role,
source/replay lineage, and exact independent consumer test pinned by the
readiness inventory. The validator proves both current and committed producer
bytes and confirms that the named consumer existed at the producer commit and
still exists in the current tree.

`receipt-set.schema.json` validates the stable receipt wrapper and exact,
repository-relative receipt fields. `scenario.schema.json` validates the
behavior matrix independently.

Normal readiness execution remains typed blocked with exit 2. Dry-run exits 0
for inspection but retains `status: schema_not_ready`, typed blockers, empty
measurements, and empty claims.
