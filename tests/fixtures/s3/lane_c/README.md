# S3 Lane C evidence

This directory contains stable, strict JSON evidence for the durable WorkGraph
runtime. The implementation source is the dispatch commit recorded in
`producer-manifest.json`; the producer commit and file digests are filled only
after the implementation commit exists. `qualification-evidence.json` remains
`waiting_on_lane_a_b` until the one permitted read-only inspection binds the
real Lane A and Lane B producer manifests, types, strict readers, fixtures, and
test IDs.

The clean-process executable proof is
`tests/e2e/test_multi_agent_process_restore.py`. It proves logical graph
restoration, terminal suppression, and unknown-effect non-replay. It does not
claim the full nineteen-point G4 integration scenario.
