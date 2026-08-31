# S3 Lane D fixtures

These fixtures qualify reader shape, privacy behavior, command UX, and bind the
integrated A/B/C producer evidence. They are consumers of runtime producer
evidence, not an independent runtime authority.

- `work-graph-events.json`: explicit candidate events used by reader tests;
- `graph-reader-cases.json`: deterministic read-model expectations;
- `privacy-cases.json`: non-echoing privacy/portability cases;
- `readiness-inventory.json`: exact source-branch and integrated producer-byte inventory;
- `consumer-patterns.json`: two unrelated user-code consumer designs; and
- `qualification-evidence.json`: truthful no-claims/no-measurements evidence.

The inventory separately binds the immutable source-lane head and the replayed
or repaired producer commit whose bytes are executed. Fixture conformance alone
is never runtime qualification.
