# S3 Lane D fixtures

These fixtures qualify reader shape, privacy behavior, command UX, and blocked
readiness behavior only. They are not runtime producer evidence and cannot make
S3 ready.

- `work-graph-events.json`: explicit candidate events used by reader tests;
- `graph-reader-cases.json`: deterministic read-model expectations;
- `privacy-cases.json`: non-echoing privacy/portability cases;
- `readiness-inventory.json`: exact A/B/C dependency inventory, intentionally blocked;
- `consumer-patterns.json`: two unrelated user-code consumer designs; and
- `qualification-evidence.json`: truthful no-claims/no-measurements evidence.

At finalization, only committed A/B/C producer manifests and executable facts
may replace the waiting inventory values. Fixture conformance is never runtime
qualification.
