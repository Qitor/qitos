# S2 Lane D fixtures

This directory intentionally contains no passing A/B/C producer receipt.
`producer-receipts.json` is the honest baseline input to the Lane D runtime
qualification runner and therefore produces `runtime_not_ready`.

A future integration owner may add a receipt only after the producer fixture
and its independent runtime qualification evidence are committed at the exact
producer commit. Sink/store schema conformance or a synthetic receipt is not
runtime evidence.
