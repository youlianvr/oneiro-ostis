# Oneiro project API routing — 2026-10-12

## Authorized scope

Use the owner's project-only OpenAI-compatible endpoint
`https://justbash-api.annenkov.me/v1` as Oneiro's primary provider, with verified
existing OmniRoute providers as fallbacks through `http://127.0.0.1:20128/v1`.
The supplied account expires **2026-10-19**, with **36 requests/minute**.
The secret was supplied in chat: rotation is recommended; never echo it, commit it,
put it in reports or change other applications to use it.

This request redirects the interrupted forum-repair pass. Preserve the existing
uncommitted repairs and parallel work. Do not edit `dream/`, restart the preview
on 9899, enable real Telegram, run improvement experiments or commit anything.
The complete approved forum plan remains in `docs/READY-2026-10-12.md` section 0.

## Ordered work and exit criteria

1. Inspect current provider/configuration code, Git ownership, available models,
   local OmniRoute health/history and relevant installed skill contracts.
   Choose fallbacks from actual existing connections and successful tool probes;
   history/current availability is evidence, not a guarantee of future uptime.
2. Reuse Oneiro's existing registry/fallback mechanism. Store the supplied key in
   an explicitly Git-ignored project-local `.env` under a unique variable name;
   never replace shared `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` variables or gateway
   configuration. Patch only the routing keys in Oneiro's own settings, preserving
   all other settings and the configuration history. Add bounded per-provider
   request pacing or fallback budget corrections only if existing code needs them.
3. Verify real primary text and tool-call responses with synthetic, non-owner
   prompts. Verify selected fallback tool capability and a real gateway reply when
   the primary is unavailable using a task-owned isolated configuration or transport
   fault injection (no disruption of the real service). Exercise expired/unauthorized,
   429, 5xx, network timeout and secret separation with focused regressions.
4. Run relevant pytest and full mypy on the final edited files; run the workspace
   document-route validator after documentation changes. Review owned diffs and
   confirm that `.env` is ignored, routing persists across a fresh process, and no
   credential appears in tracked changes or saved verification logs. Record exact
   outcomes/limits and hand back unfinished forum packages without committing.

## Acceptance

- Every role uses an explicitly resolved primary model, not an OmniRoute alias
  accidentally sent to the new endpoint.
- Fallback references explicitly resolve to the local gateway and named, verified
  models; credentials never cross providers.
- Failures, including account expiry, can reach the fallback within the declared
  call budget; retries/pacing/probes do not exceed it or falsely report success.
- Primary pacing respects 36 requests/minute for this Oneiro process; any external
  use of the same key remains outside this process's control.
- Secrets stay in ignored local configuration, not source/defaults/reports.
- Existing unrelated settings, owner graph/data, gateway accounts/combos and running
  preview remain untouched. No global client configuration changes or publication.

## Checkpoints

- Plan established. Oneiro already supports explicit provider/model references,
  independent key variables, capability probes and ordered fallbacks. No SDK is needed.
- Owner explicitly accepted request/response research logging and confirmed using
  BashAPI for ordinary Oneiro conversations, not just an isolated demo. Source:
  https://justbash-api.annenkov.me/ (researcher read the landing page).
- Configured primary `justbash/glm-5.3` for default and all three roles;
  `requests_per_minute: 36`, `timeout_seconds: 15`, and explicit browser-compatible
  User-Agent. The real model list returns HTTP 200 with **142 IDs** and lists GLM-5.3.
- Ordered fallback references:
  1. `omniroute/plusvibeapi.ru/anthropic/claude-opus-4.8`
  2. `omniroute/api-mistral-ai/codestral-2508`
  Gateway `timeout_seconds: 20`. No OmniRoute connection/combo changes.
- Selection evidence from read-only local usage metadata over seven days: plusvibe
  Opus **95/95** successful samples; Mistral Codestral connections #96 **132/132**
  and #100 **12/12**. Other Mistral keys had failures; these counts do not imply the
  entire key pool or future traffic is perfect. Both model routes passed fresh
  synthetic tool-call probes. Model names are gateway reports, not independently
  authenticated claims about upstream model identity.
- Secret names in ignored project `.env`: `ONEIRO_JUSTBASH_API_KEY` and
  `ONEIRO_OMNIROUTE_API_KEY`. The latter preserves the existing gateway key when the
  gateway moves from first to second provider (only the first may borrow the legacy
  `llm.api_key`). Shared credential files and global client variables were not changed.
- Only six routing settings were saved through `config.save`; **four unrelated
  stored settings** were checked unchanged. Previous settings are preserved by the
  existing `settings-history` mechanism. No secret was written into provider records.
- Implementation: optional provider fields `user_agent`, `requests_per_minute`,
  `timeout_seconds`; validate values at save and runtime. Pacing covers discovery,
  probes and retries; a provider's call cap includes its retry waits. Defaults remain
  unchanged for other installations. Cancellation during pacing propagates.

### Final verification evidence

Commands run from this project folder:

- `python -m pytest tests/test_models.py tests/test_config.py tests/test_chat_slice.py tests/test_settings_catalog.py tests/test_settings_honesty.py tests/test_package_foundation.py -q`
  → **146 passed, exit 0**, 70.64 s. One pre-existing Python 3.14 asyncio-policy
  deprecation warning. This is focused acceptance, not a new full-suite claim.
- `python -m mypy python/oneiro` → **45 source files, exit 0**, rerun on final code.
- `PYTHONPATH=python python -u _tmp/api-routing-live-check.py` → **exit 0**.
  Fresh process read persisted settings: primary discovery worked, but generation
  failed, and the real chain returned exact `ONEIRO_READY` through plusvibe in
  **24.08 s**; tool work returned `oneiro_probe(text=ready)` through plusvibe in
  **36.57 s**. No effectful tool was executed and no graph/data was opened.
  Evidence: `_tmp/api-routing-live.log`, `_tmp/api-routing-live-result.json`.
- Second fallback check: only primary/first-fallback calls were fault-injected in
  this check's transport; Codestral's capability probe and actual requested tool
  call traversed the real gateway → correct tool reply in **1.44 s**, exit 0.
  Evidence: `_tmp/api-routing-second-fallback.json`.
- Focused regressions cover 401/403 account rejection, 429/503 retry fallback,
  primary timeout budget, separate provider credentials, User-Agent on discovery
  and chat, 36/min rolling-window spacing with a fake clock, discovery sharing the
  pacing limit, invalid field refusal and cancellation. Pacing is per running
  registry/process; restart/other clients sharing the key are not aggregated.

**Primary limitation:** GLM-5.3, GLM-5.2, Kimi-K2.7-Code and Qwen3-Coder-Plus
all returned HTTP **503** on synthetic generation. A bounded diagnostic classified
one response as `model_unavailable`; no provider error text or key was saved.
Therefore primary routing is installed but successful BashAPI generation is **not
verified**. The fallback works under this actual outage. No new experiment was run.
The account is scheduled to expire 2026-10-19; 401/403 then use the same fallback
chain. Expiry is declared by the owner, not independently verified by an account API.

### Ownership and remaining forum work

This pass owns `.gitignore`, `python/oneiro/chat.py`, `python/oneiro/config.py`,
`python/oneiro/models.py`, `tests/test_models.py`, this report and only the provider
help-text hunk in the already-dirty `python/oneiro/settings_registry.py`.
Earlier drafts/refusal repairs and all other dirty files are preserved, unstaged and
uncommitted. `dream/`, owner graph/records, real Telegram and preview 9899 were not
modified. No new account, SDK, deployment, push or commit.

The interrupted forum plan still owes final **full-suite** verification on a stable
tree, W3 outer/individual CLI exit capture, reproducible local-demo rehearsal,
Russian 10–12 minute speech/timed rehearsal and an owner-authorized checkpoint.
This API change does not establish full product readiness or erase those packages.

- `PYTHONPATH=python python -m oneiro verify-model` → **exit 1**, correctly
  reporting primary `verified: false`, tools/vision unestablished after HTTP 503,
  and **both fallback routes usable for tools**. Six counted calls: four completed
  (two discoveries, two fallback probes) and two failed (primary tool/vision probes).
  Evidence: `_tmp/api-routing-cli.log`, `_tmp/api-routing-cli.exit`. This is a
  failed primary verification, not a passing integration claim.
- `python _scripts/validate_doc_routes.py` (workspace root) → **exit 0**.
- `git diff --check` on owned paths → **exit 0**. Verified `.env` is ignored and
  configured secrets are absent from tracked diffs, this report and all task logs.
- Probe/test background process PIDs 17500, 31864, 34256, 32704 and final CLI
  30468 completed; no new persistent service remains. The interrupted repair
  preview and owner's 9899 server were not stopped/restarted by this API pass.

**Delivered:** routing saved and both reserves demonstrated; primary outage remains
an external blocker. All source edits remain uncommitted.

## Active working route — owner decision, 2026-10-13

The owner said **Mistral if BashAPI cannot answer** and directed finishing the forum
plan. Default and manager/researcher/executor are now explicitly
`omniroute/api-mistral-ai/codestral-2508`. Provider records, secrets, pacing caps and
the original fallback list were checked unchanged. Primary registry text/tool
calls both succeeded; evidence `_tmp/forum-mistral-primary.json` records
`ONEIRO_READY` and `oneiro_probe(text=ready)` served by `codestral-2508`.
BashAPI remains available as a configured provider, not the active role/default.
The later diagnosis below describes the prior route, not current live selection.

## Follow-up: diagnose primary model_unavailable (2026-10-13)

Owner request: diagnose BashAPI and establish an actual primary answer **without
changing the reserves**. Preserve the existing fallback references, gateway provider
record, credential variables, unrelated settings and dirty working base byte-for-byte.
No effectful tools, owner conversation/data, preview restart, service provisioning,
commit or gateway reconfiguration.

Ordered packages / acceptance:
1. Inspect bounded, sanitized error details and fresh advertised model metadata;
   compare synthetic requests via the current production transport and minimal
   compatible request variants. Do not assume catalog visibility proves availability.
   Stop at a real authorization refusal; never bypass an access restriction.
2. Repair a demonstrated request incompatibility or select an actually responding
   advertised primary model if needed; do not silently call a fallback and attribute
   it to BashAPI. Keep existing secrets/limits and reserves unchanged.
3. Confirm text and tools through a fresh Oneiro registry with ledger entries naming
   **justbash** and the returned model; test the user-facing HTTP/CLI path where
   practical without opening owner graph/data. Rerun affected tests/types only if
   source is edited. Record failures, exact exits and unchanged-reserve evidence.
4. Update this report with cause/evidence. If the provider has no available upstream,
   report the external blocker honestly instead of claiming a local repair worked.

### Findings and limits

- Authenticated `GET /v1/models` succeeds and advertises GLM-5.3 with tools and
  `max_tokens`/`stream` support. This proves catalog access, **not** generation
  entitlement, upstream health or real model identity.
- Fresh OpenAI requests with the exact production shape and then with explicit
  `stream: false` / `max_tokens: 64` both return HTTP 503:
  `{"error":{"message":"Model is temporarily unavailable, please try again later","type":"model_unavailable","code":"model_unavailable"}}`.
- Seven distinct advertised IDs checked this pass: `glm-5.3`, `deepseek-chat`,
  `qwen3.5-flash`, `deepseek-v4-flash`, `glm-5.1`, `MiniMax-M2.5`, `qwen3.8-max`.
  All returned the same unavailable error. The earlier pass additionally failed
  GLM-5.2, Kimi-K2.7-Code and Qwen3-Coder-Plus. No responding model was found;
  it would be unjustified to change the primary to another unverified catalog ID.
- GLM-5.3 with `stream: true` still returns HTTP 503 before any event stream;
  the advertised Anthropic-compatible `POST /v1/messages` with `x-api-key` and
  `anthropic-version: 2023-06-01` also returns HTTP 503 `model_unavailable`.
  This was a compatibility check, not an attempt to bypass a permission refusal.
  No 401/403 was returned and no alternative host/key was tried.
- The saved seven-case matrix returned errors in **0.47–1.24 s**; a later production
  text request failed in **1.02 s**, below the configured 15-second budget.
  This is a provider response, **not** a client-side timeout. Neither omitting nor
  adding `stream`/`max_tokens`, changing model family or API interface resolved it.
- Public research found no server implementation or maintainer guidance for this
  error. The landing page (https://justbash-api.annenkov.me/) advertises both APIs;
  `/docs` and `/openapi.json` are 404 according to the researcher's fetches.
  No public evidence establishes model mapping, circuit breakers or per-account
  generation permissions. An upstream outage, routing/configuration problem or
  account-specific entitlement failure remains possible; **the internal cause is
  not proven** and needs the operator's server logs.

### Exit evidence

- `PYTHONPATH=python python -u _tmp/bashapi-diagnose.py` → **exit 0**, seven
  completed diagnostic cases, all generation attempts failed with HTTP 503.
  The script's exit is diagnostic completion, **not** a successful primary check.
  Artifacts: `_tmp/bashapi-diagnosis.json`, `_tmp/bashapi-diagnose.log`,
  `_tmp/bashapi-diagnose.exit`.
- Direct production `Registry._ask` for text and `Registry.probe` for tools with
  fresh persisted routing → text **503**, tools **unestablished**, no fallback
  called. Evidence `_tmp/bashapi-primary-oneiro.json`: `provider: justbash`,
  `requested_model: glm-5.3`, `text_verified: false`, `tools_verified: false`.
  The probe ledger records one failed primary call; `_ask` is the underlying
  transport seam and does not itself open a ledger entry.
- Before/after comparison of **all** stored `models.*` keys passed. No primary,
  fallback list, gateway record, role selection or credential was changed.
  `_tmp/bashapi-routing-before.json` holds non-secret routing metadata only.
- No application/test code was edited in this follow-up, so earlier passing tests
  and mypy were not rerun. Document routes revalidated after this report edit.
- Diagnostic PID **15804** stopped; all saved follow-up scripts/results/logs were
  scanned against both configured keys and contain neither. No graph/owner data
  or running previews were used. Nothing committed or sent to the maintainer.

**Result: blocked externally.** Primary generation remains unverified and could
not be made to answer by any demonstrated local correction. The local request
shape/timeout hypothesis was not supported by the controlled checks. Reserves
remain unchanged. Required next evidence is the BashAPI operator's reason for
`model_unavailable` on this account, and then a successful synthetic text/tool
response through Oneiro's primary registry.

### Maintainer handoff (no secret; not sent)

> Authenticated `/v1/models` returns 200, but `/v1/chat/completions` returns 503
> `model_unavailable` for GLM-5.3 and multiple listed Qwen/DeepSeek/MiniMax models.
> Minimal text requests, explicit `stream:false` + `max_tokens`, streaming and
> Anthropic `/v1/messages` produce the same error in about one second. Can you
> check whether generation is enabled for the account and which upstream/model
> is available? Please identify the server-side rejection reason. No key should
> be posted in a public issue or channel.

