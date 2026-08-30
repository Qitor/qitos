# Trajectory readiness fixtures

This stable directory contains Lane D readiness inputs, not producer schemas or
Trajectory payloads. `contract-qualification-receipts.json` preserves the two
accepted G1 foundation bindings and independently binds all 17 G2 A/B/C
contracts to their reviewed semantic-owner bundles. These receipts qualify
contract bytes only; they do not establish runtime or Trajectory readiness.

`scenarios.json` is a schema-checked inventory of required readiness behaviors.
Scenario availability labels are test instructions. Adversarial tests construct
a temporary Git repository, commit synthetic fixture/evidence bytes, and
compute their exact identities at runtime. Repository receipts use only the
reviewed producer versions, commits, paths, digests, and authority pinned by the
readiness inventory.

`receipt-set.schema.json` validates the stable receipt wrapper and exact,
repository-relative receipt fields. `scenario.schema.json` validates the
behavior matrix independently.

Normal readiness execution remains typed blocked with exit 2. Dry-run exits 0
for inspection but retains `status: schema_not_ready`, typed blockers, empty
measurements, and empty claims.
