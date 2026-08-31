# S3 Lane A producer bundle

This directory freezes the Session-fork and ownership-fencing facts produced by
Lane A. Consumers must validate `producer-manifest.json`, verify every listed
SHA-256 digest, and use the strict readers named there. Identity relationships
are explicit; identifier text and file names carry no lineage semantics.

`fork-ownership.json` contains a deterministic fork receipt, lineage component,
and generation-zero child head. `failure-matrix.json` records supported typed
failure and crash-window behavior. `qualification-evidence.json` separates
qualified local runtime facts from unsupported distributed/exactly-once claims.

Lane C should import `Session` from `qitos.engine.session_runtime`,
`SessionForkReceipt` from `qitos.checkpoint.session`, and the typed lineage
component from `qitos.core.session`. Lane D should read the same receipt and
snapshot component; neither consumer may copy the vocabulary or parse IDs.
