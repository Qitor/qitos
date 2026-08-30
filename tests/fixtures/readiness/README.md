# Trajectory readiness fixtures

This stable directory contains Lane D readiness inputs, not producer schemas or
Trajectory payloads. `contract-qualification-receipts.json` preserves the two
accepted G1 foundation bindings. It does not qualify any S1 A/B/C producer and
does not establish G2 readiness.

`scenarios.json` is a schema-checked inventory of required readiness behaviors.
Scenario availability labels are test instructions only: tests construct a
temporary Git repository, commit synthetic fixture/evidence bytes, and compute
their exact identities at runtime. No S1 producer version, commit, path, digest,
authority, fixture content, or qualified status is fabricated here.

`receipt-set.schema.json` validates the stable receipt wrapper and exact,
repository-relative receipt fields. `scenario.schema.json` validates the
behavior matrix independently.

Normal readiness execution remains typed blocked with exit 2. Dry-run exits 0
for inspection but retains `status: schema_not_ready`, typed blockers, empty
measurements, and empty claims.
