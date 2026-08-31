# Context-transfer producer fixtures

`v1/semantic_fixtures.json` is the Lane B semantic matrix for the strict
`ContextTransferPlan` and `ContextTransferReceipt` candidates. The producer test
reads this exact file and verifies that every declared case remains represented
by an executable offline test category.

The final `producer-manifest.json` is generated only after the implementation
commit exists, so its `producer_commit` can identify committed producer bytes.
It intentionally does not claim scheduler or S3 convergence readiness.
