# Confirmation release v1

The supplied task is the specification. Build a small offline release layer over
controlled-v1 preparation, controlled-run-v1 and controlled-analysis-v1. No model
requests, downloads, generator changes, new metrics or statistical engines.

Use 19 cells: chain/math noise K=4 N=8,16,32; separate chain K=3,4,6 and math K=2,4,6
at N=16; all seven topologies at N=16 (direct 2, chain/math/merge 4,
coverage/idem/fork 3). Seeds 2718281,3141593, 128 pairs each: 256 independent
families per cell, 2816 unique families, 9728 cases. Three existing grid models,
both strategies: 58368 requests, provisional output cap 2048, timeout 120s,
three attempts. These settings are frozen proposals requiring development
calibration and a new release if changed. Unknown model facts stay null.

Approaches: prose alone cannot enforce integrity; a new execution/statistics
stack duplicates PRs 2–7. Chosen implementation is strict release schemas,
inventory and content-addressed manifest, prospective AnalysisPlan with logical
run names, technical UUID binding, and minimal offline runner initialization.
This is an implementation decision under the user's explicit detailed brief.

Freeze scientific files before the sole preparation. Keep full failed artifacts
in an ignored bundle, a portable archive and hashes; commit compact receipts.
Verification reuses dataset gates, preflight and saved snapshot validation.
Separate scientific freeze, dataset admission, profiles, backend, real smoke,
binding and launch readiness. Unknowns and missing evidence fail closed.
Do not change historical files or publish tags/releases/archives.
