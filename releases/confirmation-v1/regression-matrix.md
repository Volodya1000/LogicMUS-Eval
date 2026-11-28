# Regression evidence A–K

No real model or endpoint was used. The final full suite contains 447 passing
tests; the new release test module contains 29. Existing PR #2–#7 tests remain.

| Requirement | Evidence |
|---|---|
| A. Failed dataset blocks | Existing `test_failed_whole_series_blocks_preflight`; new `test_failed_dataset_cannot_be_sealed_as_admitted`; actual preparation verdict retained separately |
| B. Changed data/plan/profile/budget/analysis detected | Parameterized `test_changed_release_artifact_blocks`; the whole RunConfig file is hashed, covering profile and generation/timeout budget fields; all source and dependency versions also checked |
| C. Unknowns/placeholders never ready | `test_release_separates_data_admission_unknown_profiles_and_missing_smoke`, `test_placeholder_profile_cannot_be_complete` |
| D. UUID binding preserves science | `test_initialize_is_offline_and_binding_only_substitutes_uuid`; exact ordinary AnalysisPlan equality after substituting run_ids only |
| E. Bad/incomplete contrasts rejected before HTTP | Five `test_bad_contrasts_rejected_before_http` cases; `test_prospective_template_validates_exact_pairs`; `test_group_incompatibility_without_contrasts_rejected` |
| F. Counts match runner, combined not double counted | `test_inventory_counts_families_once_and_matches_runner` uses actual admitted runner preflight |
| G. Reused families remain one | `test_family_reuse_across_series_is_not_independent`; inventory explicitly reports unique families and family/cell occurrences |
| H. Offline check/init do not call endpoint | `test_release_checks_and_initialization_do_not_import_network` rejects even network-module imports; all initialization and binding tests have empty journals |
| I. Missing real smoke stays not_verified | Missing-smoke status assertion; `test_fake_smoke_pass_flag_is_rejected`; `test_stub_smoke_analysis_is_not_evidence` |
| J. Mock end-to-end path | `test_mock_path_initialize_bind_resume_verify_analyze`, provenance verification and actual existing analyzer; `test_verified_smoke_analysis_then_stale_provenance_rejected` |
| K. Historical artifacts unchanged | Git diff against base contains no changes under data/datasets/experiments; existing analysis tests verify source report hashes remain unchanged |

Additional regressions cover an already-started binding, locks held through
binding persistence, complete development calibration, truncation/timeouts,
and gated explicit indeterminate retry without repeating finalized jobs.

Copy integrity is verified separately for both exact source archive extraction
and Git reconstruction with SHA256-checked LF/CRLF restoration. Scientific
contract recovery alone remains blocked until the data bundle and real evidence
are supplied; this is expected fail-closed behavior.
