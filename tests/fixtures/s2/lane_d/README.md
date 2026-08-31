# S2 Lane D fixtures

`producer-receipts.json` binds the G3 integrated A/B/C runtime evidence to its
exact producer commit and SHA-256 bytes. The default qualification input now
produces `s2_runtime_ready` for the twelve required runtime scenarios.

This does not qualify or freeze the candidate Trajectory schema, enable its
writer by default, migrate qita, or establish publication/performance claims.
Those remain independently blocked.
