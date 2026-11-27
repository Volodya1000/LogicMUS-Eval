# Resumable controlled execution

This runner executes an **already admitted** PR #5 `series.manifest.json`. It never
generates, repairs, samples or substitutes datasets. It shares the existing strategies,
response parser, `build_case_report`, metrics version 3 and process-isolated Z3 protocol
1. Legacy `evaluate`/grid commands retain their historical behavior and do not acquire
these durability guarantees.

## Configuration and commands

Copy [the small example](../examples/controlled-run.example.json) and supply the
admitted manifest and explicit served model selection. The example's unknown profile
fields are intentional; it is not an admitted confirmation experiment. Paths inside a
JSON configuration resolve relative to that configuration file.

```powershell
# OFFLINE: no client import, endpoint request, model load or download.
uv run logicmus-eval experiment-preflight --config examples/controlled-run.example.json

# These two commands contact the model. Do not run them as development checks.
uv run logicmus-eval experiment-start --config examples/controlled-run.example.json --run-dir experiments/paper-dev-01
uv run logicmus-eval experiment-resume --run-dir experiments/paper-dev-01

# OFFLINE: recheck saved conditions, current code, journal, and remaining work.
uv run logicmus-eval experiment-preflight --run-dir experiments/paper-dev-01

# Optional candidate config must be identical, otherwise resume is rejected.
uv run logicmus-eval experiment-preflight --config examples/controlled-run.example.json --run-dir experiments/paper-dev-01

# Only after inspecting an unresolved HTTP attempt and accepting possible cost:
uv run logicmus-eval experiment-resume --run-dir experiments/paper-dev-01 --indeterminate-policy retry
```

`experiment-start` refuses an existing directory. `experiment-resume` reads
`run.manifest.json`, never a report or a mutable external config as authority. Optional
`--config` checks a proposed config against the saved one. Credentials are supplied
through the named `api_key_env` variable only; the credential value is not part of the
manifest/request hash. A credential-free endpoint sends no Authorization header. The
transport never selects credentials or proxies from the environment implicitly. Do not
embed credentials in model IDs, endpoint paths or user profile facts. Endpoint
credentials, query strings, fragments and unknown configuration keys are rejected. The
runner targets an explicit OpenAI-compatible chat endpoint; it is not a provider/model
lifecycle manager.

The offline command checks the whole series again, including all cell datasets,
reference artifacts, recorded admission evidence, plan hash and combined file. It checks
exact cell membership and controlled case provenance. **Only cell datasets supply
jobs**; the combined file is an integrity cross-check. Each `case_uid × model × strategy
× inference-identity` occurs once. The preflight output lists counts per
cell/model/strategy, complete budgets and all unknown or unconfirmed conditions. It
fails if any planned cell is absent or unapproved.

`generation.max_tokens` is mandatory and positive. Temperature, optional top-p, seed and
reasoning effort are recorded per model. Request socket-operation and Z3 wall-clock
timeouts, transient retry classes (including optionally `api_unavailable` for HTTP
500/502/503), maximum attempts and exponential backoff bounds are explicit. The
normalized manifest records defaults as well. The raw JSON HTTP transport has no built-
in retries, redirects, implicit proxies, prompt rewriting or parameter dropping; an
unsupported parameter becomes a recorded API failure, without silently removing it.
JSON/schema/logic/Z3 errors are final outcomes and never trigger automatic model retries
or budget changes. The same messages and parameters are reused for explicit transient
retries. The HTTP timeout bounds socket operations; a server continuously trickling data
can extend total request time. The runner does not claim a hard end-to-end HTTP
deadline. Add an external process deadline when that bound is required; its termination
leaves a conservatively indeterminate attempt.

## What is recorded and checked

`run.manifest.json` has a run UUID, creation time, immutable normalized config, exact
ordered inventory and request hashes, original series/plan hashes, actual Python source-
bundle hash, Python/Pydantic/Z3 versions and HTTP adapter protocol, metric/report
versions, response-schema/request identity and Z3 protocol. Changing any of these
conditions rejects resume **before HTTP**, including uncommitted source edits. The
executable source hash is independent of Git HEAD. Keep the checkout and dependencies
fixed for the run; source files must not be edited during execution. Moving the original
series path also requires a new run under this conservative identity policy. No
automatic migration weakens these checks.

Per attempt/outcome the journal retains the actual client messages, generation and
transport parameters, full structured-response JSON schema, canonical SHA-256 request
identity, response envelope with original UTF-8 body text, HTTP status,
choices/content/usage, available IDs, finish reason, measured request time, and
classified outcome. HTTP headers are excluded except the allowlisted x-request-id. The
controlled runner uses stdlib urllib directly: SDK retries, prompt repairs and usage
normalization cannot silently change its requests or observations. Known credential
strings and sensitive response keys are redacted before persistence; hashes refer to the
retained, sanitized envelope. Exception messages from providers are replaced by a
classification and exception class because they can contain secrets.

Model profile fields cover served identifier, revision/file, quantization, context,
backend version, chat template and tokenizer. Configured facts are labeled
`user_supplied`; response model ID and system fingerprint are `observed`. Explicit
profile fields in an optional server `model_info` object are also recorded as observed;
known contradictions with supplied facts or previously observed profile values stop
further HTTP. A response model alias is not proof of a revision, file or tokenizer.
Unobserved facts remain unknown/unverified, including supplied profile facts that the
server does not attest. `confirmed_settings: null` explicitly records that this endpoint
adapter has no trustworthy parameter echo. Accepting a request is not proof that the
backend applied every setting. Set `expected_profile.served_model_id` to require the
exact observed response model ID; a missing/different ID finalizes a profile error and
stops further HTTP, including subsequent resumes. Other profile assertions are recorded,
not falsely presented as automatic loaded-model verification. If such verification is
needed, perform a separate backend-specific operator check; offline preflight does not
claim to perform it. No probe, load or download happens automatically.

There is no trustworthy tokenizer available to this adapter, so input token counts and
context fit are explicitly unknown. It does not estimate exact counts or truncate input.
It rejects an output budget that already exhausts the supplied context and records
server context-window errors as `context_error`. Omitted usage stays `null`, not zero.
`finish_reason=length` is `generation_truncated`, even when the partial payload is
malformed JSON or valid JSON. Partial generated code is not executed in that case.

## Crash recovery and durability boundaries

The authoritative `journal.sqlite3` is an append-only event history with transactional
sequence numbers, SHA-256 chaining, a separately stored committed tail, and a unique
index for finalized job IDs. SQLite integrity and event state validation run before
continuation. An exclusive OS file lock on `writer.lock` covers the entire write
session; a second process fails instead of appending. The file remains on disk, while OS
ownership is released on normal exit or process death. Do not remove/replace the lock
file or open SQLite manually while the runner owns the directory.

| Crash stage | Durable state and next action |
| --- | --- |
| Initialization before both manifest and journal exist | No HTTP has started; incomplete initialization is rejected, never treated as resumable results. Use a new directory. |
| Before request intent commits | Pending; no call has been issued by the runner. |
| After intent commits, before/during HTTP or before response commits | In-flight becomes indeterminate on recovery. Default resume halts before any new HTTP. |
| During response/error transaction | SQLite restores the previous committed prefix. Intent remains visible; no torn payload is silently ignored. A committed API error resumes under the same explicit retry policy. |
| After raw response commits, during parsing or isolated Z3 | Response awaits processing; resume reuses it with no HTTP. Z3 may execute again; usage and outcome count once. |
| During outcome transaction | Prior cases remain committed. If outcome committed, skip it; otherwise process its saved response/error. |
| After finalized outcome commits, before next case | Correct answers, errors and refusals are all final and never automatically rerun. |
| During report snapshot | Journal remains authoritative. Stale/missing/torn reports are rebuilt on compatible resume. |

**Exactly-once HTTP is impossible here.** An intent may precede a call that never left
the machine, or an expensive completed server request whose response was lost. Both are
conservatively indeterminate. `--indeterminate-policy retry` appends an explicit
resolution preserving the old intent, possible server processing and unknown cost, then
starts a fresh configured retry cycle. A crash after that resolution does not erase the
permission or the uncertain attempt. The original attempt remains in history, request-
attempt counts and unknown-cost diagnostics. Transient timeouts/connection/rate-limit
retries are similarly recorded, and missing costs are never invented. Metrics retain PR
#3 accounting: `token_accounting_complete` is false when a case needed multiple
attempts.

SQLite uses rollback journaling and `synchronous=EXTRA` (FULL plus journal-unlink
directory sync). Every intent, raw response/error and outcome commits separately before
the next dependent action. On process termination, SQLite transactions recover as all-
or-nothing. Power-loss durability depends on a local filesystem, working OS flushes and
storage honoring sync requests; hardware/OS failures can defeat these guarantees.
Network filesystems, cloud-sync folders, live directory copies, manual modifications and
disk loss are not covered. Keep the whole run directory together and back it up only
when no writer owns it. Integrity/hash failures and missing tail records stop execution;
no automatic truncation or repair discards ambiguous evidence. Checksums are corruption
detection, not cryptographic signatures against a party who rewrites both data and
hashes.

## Reports, provenance verification and diagnosis

`report.json` and `reports/<model-strategy-hash>.json` are atomic projections from
finalized journal outcomes, using the existing metric implementations. The root report
covers all jobs; each subgroup report gives per-model/strategy metrics. The journal
head/count, run/config/source identities and global pending, indeterminate, unknown-cost
and finalized counts accompany the reports. Completeness means all planned outcomes are
finalized; model errors/refusals do not make a complete report incomplete. Unresolved
intents and saved responses awaiting processing do not count as finalized. Reopening a
completed run makes no HTTP calls and reproduces its stored outcomes and metrics.

To verify saved provenance without contacting an endpoint:

```python
from pathlib import Path
from logicmus_eval.evaluation.reports import verify_runner_report

report = verify_runner_report(Path("experiments/paper-dev-01/report.json")) ```

This compares the report's identity, manifest and committed journal head, then rebuilds
its metrics and details from the saved outcomes. It rejects stale or modified reports.
It checks the historical saved source identity, whereas resume also requires the current
source bytes to match. Historical JSON still loads through `EvaluationSummary`/existing
readers; new optional fields stay `None` when missing and never retroactively attest
historical inference/durability.

Diagnostic reruns use **a new directory** with `diagnostic_parent_run` set to the
original run UUID (and a separate config if conditions change). The primary failed
outcome is never replaced by a more successful diagnostic result.

## Development validation and remaining scope

All API scenarios in regression tests use mocks with zero retry delays. Tests cover
interruption/resume, errors/refusals, metric reconstruction, transactional process
death, physical/logical journal corruption, committed-tail loss, competing processes,
source/prompt/schema/config/protocol incompatibility, indeterminate history, raw/API-
error/Z3 replay, truncation, unknown usage, context errors, secret exclusion, whole-
series rejection and offline import isolation. No real model request or model download
is part of these checks.

This implements runner mechanics, not the final confirmation dataset or its statistical
analysis. A large confirmatory paper run is not declared ready until the final dataset
has been frozen and admitted, and necessary backend/model conditions have been
independently verified.

Validation on the implementation: `python -m pytest -q --tb=short` — **374 passed**;
`python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy`,
and `python -m pylint logicmus_eval` passed. Pylint also passed for the three new
test modules. The JSON example validates offline. Commands assume dependencies
are already installed; use `python -m logicmus_eval.cli ...` when you need to
avoid the package manager performing any dependency synchronization.

Interrupted end-to-end case time is unknown (`null`) on recovered processing.
An indeterminate attempt also leaves total LLM latency unknown; the observed
per-attempt request times remain in the journal. This avoids presenting the
short replay time as the complete duration of the original case.
