# Finalizing confirmation-v2 later

This candidate is not the executable confirmation-v2 release. Its receipt cannot
replace `release.manifest.json`, preparation sealing, backend/smoke evidence,
AnalysisPlan UUID binding or admission. Existing `release-initialize` rejects
this directory; there is no executable release spec or manifest here.

## Operator's next action

Establish full HTTP input accounting for the installed backend and its effective
model/template/tokenizer/runtime/defaults. In particular, establish how the
exact `response_format` JSON schema enters the actual prompt; its token cost is
unknown. The saved SDK template-only counts cannot supply this evidence.
Do this before authorizing any real smoke. This PR performs no generation,
model load/unload, start/resume or backend calibration requests.

Keep two gates separate:

1. The existing standalone development-smoke is checked against its **full
   admitted development parent**, including its original fixed selection.
   Preserve PR #10's negative template-only diagnosis (direct 2444/2302,
   z3 3791/3672 target/smoke maxima). It is not exact HTTP accounting and it
   does not establish coverage, even assuming zero schema overhead.
2. A release-smoke must cover **every exact confirmation request** under the
   final conditions, per model/strategy. Candidate preflight requests are exact
   only for the proposed conditions; changed conditions require fresh inventories.
   Passing either gate never transfers to the other.

## Separate proposal if selection remains insufficient

Do not change the current eight-case selection to obtain passed. A separate PR
could define and prospectively freeze a deterministic input-based selection rule
covering both strategy maxima for each verified model/tokenizer and all required
Boolean/numeric SAT/UNSAT categories. It must first show the old rule's failure,
state the full target inventory and tie-breaks, retain its negative evidence,
and independently check both gates above. This is a proposal only; no new rule,
new subset, new sample, new admission or successful smoke is created here.

## Required order after backend verification

1. Resolve full HTTP accounting and effective profiles without assuming Hub
   defaults or embedded GGUF templates are active. Recheck current instances:
   PR #10's Qwen context 12288 is a dated observation; Gemma/GPT-OSS active
   contexts/templates/runtime remain unknown. Coordinate model loading with
   the operator outside this task.
2. Under a separately authorized protocol, run real development smoke, preserve
   every HTTP attempt, completion, error and wrong answer; obtain provenance,
   usage/context evidence, completed no-op resume and diagnostic analysis.
   Confirm output cap 2048 and request timeout 120s by development calibration.
   Apply the inherited prospective budget rules if calibration fails; never
   calibrate against confirmation correctness or discard failed smoke evidence.
3. Recompute exact confirmation preflight requests under the calibrated future
   configs and verify release-smoke coverage, schema overhead and active context
   independently of standalone-parent coverage. The main retry policy has three
   attempts per job; the historical smoke policy has one.
4. Construct a **new** `releases/confirmation-v2` with final RunConfigs, the same
   intended scientific design and updated AnalysisPlan identities. Use existing
   `release-freeze` only after all configuration decisions are settled, before
   final execution and UUID binding. Preserve this candidate and its receipt.
5. Only reuse the prepared candidate data if exact bytes, plan identities,
   generator/source hash, dependency environment, saved SMT/reference checks,
   leakage and the single-attempt provenance all verify. Retain both the candidate
   receipt and raw-file index as the origin chain. Changed generation/source or
   scientific conditions cannot be concealed by rewriting hashes.
6. Use preparation sealing, backend/smoke checking, `release-check`, then
   `release-initialize` for prospective UUID binding and admission before any
   confirmation HTTP. Scale is allowed only when all existing gates pass.

## Current command limitation

The current CLI has no candidate-import/handoff command that verifies this
receipt and its one-attempt provenance. `release-freeze` binds final configs
and current sources; `release-seal-preparation` can inspect existing local
files, but it does not import candidate provenance or prove the handoff. A
manifest generated with different source bytes fails the later source gate.
Moving files alone does not establish compatible runner paths or provenance.

Therefore data reuse needs an explicit reviewed handoff procedure or a narrowly
scoped follow-up implementation before final admission. Do not copy a candidate
receipt into a release manifest, manually edit checksum fields, relabel the
candidate admitted, rerun preparation to seek a better leakage result, or weaken
existing freeze/SMT/leakage/context/HTTP checks. If safe reuse cannot be shown,
retain blocked and decide the next version/protocol explicitly.
