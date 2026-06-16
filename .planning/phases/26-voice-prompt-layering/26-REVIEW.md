---
phase: 26-voice-prompt-layering
reviewed: 2026-06-16T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - frontend/src/App.tsx
  - frontend/src/api.ts
  - frontend/src/components/SoftSegurosSetup.tsx
  - frontend/vite.config.ts
  - backend/cobranza/voice_pipecat.py
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-06-16
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Reviewed the uncommitted working-tree changes for the voice debt-collection demo
(Twilio + Gemini Live, `backend/cobranza/voice_pipecat.py`) and its React frontend
(`App.tsx`, `api.ts`, `SoftSegurosSetup.tsx`, `vite.config.ts`).

Targeted context verified:

- **Rules-of-hooks fix in `App.tsx` is correct.** The `useQuery(['emailStatus'])`
  call (lines 1676-1681) is now placed *above* the `if (!user)` / `if (showOnboarding)`
  early returns (1683-1684), and `useQueryClient` (1613) plus every `useEffect`/`useState`
  sit before those returns too. No conditional-hook violation remains in `App`. The
  per-view components (`ViewInicio`, `ViewAprobados`, etc.) also call their hooks
  unconditionally at the top. No other rules-of-hooks violations found in the changed file.

- **CORS 400 on OPTIONS preflight is almost certainly NOT caused by any file in scope.**
  In dev (`import.meta.env.DEV`), `API_BASE` is `""` and all traffic goes through the Vite
  proxy (`vite.config.ts`), which is same-origin — so the browser issues **no** CORS
  preflight at all for `/api/cobranza/*`. A 400 on `OPTIONS` therefore points at the
  backend CORS middleware in `backend/main.py` (OUT OF SCOPE) — either CORSMiddleware is
  registered after a router/middleware that 400s unmatched OPTIONS, or the request is
  hitting prod (`https://my.landatech.org`) directly rather than the proxy. See WR-01 for
  the in-scope contributing factor.

The most serious in-scope issues are a broken money-formatting path that produces wrong
spoken amounts (CR-01) and an unbounded LLM-cost / dead-air risk because `MAX_CALL_SECONDS`
does not actually hang up the call (CR-02).

## Critical Issues

### CR-01: Money formatting can speak the WRONG amount to the debtor

**File:** `backend/cobranza/voice_pipecat.py:163-168`
**Issue:** The `monto_natural` formatting chains `.rstrip('0').rstrip('.')` onto an
f-string that includes the literal suffix `" millones de pesos"` / `" mil pesos"`. Because
the suffix ends in `s` (not `0` or `.`), the `rstrip` calls are harmless on the suffix —
but the rounding/formatting logic is still wrong for whole-thousands values that are not
whole-millions. Worse, the branch ordering means a value like `1_500_000` produces
`f"{1.5:.1f} millones de pesos"` → `"1.5 millones de pesos"`, then `.rstrip('0').rstrip('.')`
is applied to the WHOLE string. Since the string ends in `"pesos"`, nothing is stripped —
correct here by luck. But `monto = 1_000_000` takes the `%1_000_000 == 0` branch →
`"1 millones de pesos"` ("1 millones" is grammatically wrong; should be "un millón").
And critically, the `rstrip` is being applied to the units suffix rather than to the
number, so any future change to the suffix (e.g. ending in a stripped char) silently
corrupts the amount. The agent literally speaks money figures to debtors — an off-by-a-
decimal or truncated amount is a correctness/trust failure on a collections call.
**Fix:** Format the numeric part in isolation, then append the suffix:
```python
def _natural_money(monto: float) -> str:
    if monto >= 1_000_000:
        n = monto / 1_000_000
        num = f"{n:.0f}" if monto % 1_000_000 == 0 else f"{n:.1f}".rstrip('0').rstrip('.')
        unidad = "millón" if num == "1" else "millones"
        return f"{num} {unidad} de pesos"
    if monto >= 1_000:
        n = monto / 1_000
        num = f"{n:.0f}" if monto % 1_000 == 0 else f"{n:.1f}".rstrip('0').rstrip('.')
        return f"{num} mil pesos"
    return f"{monto:.0f} pesos"
```
Also guard against `monto` being a non-numeric type (see WR-02).

### CR-02: Call-duration watchdog does not hang up — unbounded Gemini Live cost / channel starvation

**File:** `backend/cobranza/voice_pipecat.py:985-998` (and contrast with `_handle_end_call` at 707-724)
**Issue:** The watchdog comment explicitly cites a real incident ("a voicemail call ran
280s ALONGSIDE the next real call, starving it"). The fix it implements only does
`await task.queue_frames([EndFrame()])`. But the code's OWN `_handle_end_call` handler
(lines 708-717) documents that **`EndFrame` is deferred by Gemini Live "until the bot turn
is finished" and after a tool call often never completes, leaving the line open ~30-50s** —
which is exactly why `end_call` uses `task.cancel()` instead. The watchdog uses the known-
broken `EndFrame` path, so on a voicemail (where no turn ever completes) the 240s cap will
NOT reliably terminate the call. The pipeline can keep streaming audio to/from Gemini Live
well past the cap, which is both an unbounded-cost risk (paid speech-to-speech minutes) and
the channel-starvation bug the watchdog was meant to kill. This is the demo's primary
unbounded-cost vector.
**Fix:** Mirror `_handle_end_call` and hard-cancel:
```python
async def _call_watchdog():
    await _asyncio.sleep(MAX_CALL_SECONDS)
    logger.warning("[VOICE] Watchdog: call %s exceeded %ds — forcing hang-up", call_sid, MAX_CALL_SECONDS)
    await task.cancel()   # EndFrame is deferred by Gemini Live; cancel drops the WS immediately
```

## Warnings

### WR-01: `apiCall` POST/PATCH/DELETE error path can throw on 401 vs non-401 inconsistently; OPTIONS not handled but contributes to CORS confusion

**File:** `frontend/src/api.ts:91-137`
**Issue:** Every cobranza/debtor call goes through `apiCall`, which always sets
`Content-Type: application/json` (line 103) even for bodyless GET requests. When the
frontend is (mis)pointed at the prod origin instead of the Vite proxy, a request carrying
a non-simple header (`Content-Type: application/json` + `Authorization`) forces the browser
to send a CORS **preflight OPTIONS** — which is the 400 you are observing. Within these
files the contributing factor is that the dev/prod switch (`import.meta.env.DEV`) is the
only thing keeping traffic same-origin; if the demo is served from a production build
(`DEV` false) against a backend whose CORS middleware mishandles OPTIONS, every cobranza
call preflights and 400s. Root cause lives in `backend/main.py` (OUT OF SCOPE) but the
frontend has no fallback/diagnostic.
**Fix:** Confirm the demo is actually running `npm run dev` (so `API_BASE === ""`); if it
must run a built bundle locally, add the backend origin to `API_BASE` AND ensure
`backend/main.py` registers `CORSMiddleware` (with `allow_methods=["*"]`,
`allow_headers=["*"]`) before any router that returns 400 for unmatched OPTIONS. Do not
send `Content-Type: application/json` on bodyless GETs to reduce needless preflights:
```ts
const headers: Record<string,string> = {};
if (options.body) headers["Content-Type"] = "application/json";
```

### WR-02: `monto` / policy money fields assumed numeric — `TypeError` crashes prompt build

**File:** `backend/cobranza/voice_pipecat.py:124, 163-168`
**Issue:** `monto = debtor.get("monto", 0)` then `monto >= 1_000_000` and `monto % 1_000_000`.
If Soft Seguros sync ever stores `monto` as a string (e.g. `"1500000"` or `"1.500.000"`)
or `None` (an explicit null in Mongo defeats the `.get` default), the comparison/modulo
raises `TypeError` and the whole `run_bot` aborts before the pipeline starts — the call
connects and then dies silently. The policy helpers `_p_money` (184-188) correctly wrap
`float()` in try/except, but the top-level `monto` path does not.
**Fix:** Coerce defensively: `try: monto = float(debtor.get("monto") or 0)` / `except
(TypeError, ValueError): monto = 0.0` before the formatting block.

### WR-03: Tenant `voice_system_prompt` override silently DROPS all policy/debtor data and tool guidance

**File:** `backend/cobranza/voice_pipecat.py:319-328`
**Issue:** When a tenant has set `voice_system_prompt`, the code does
`system_prompt = tenant_prompt[:2000]` — **completely replacing** the 6500-char base prompt,
including the `DATOS DE ESTA LLAMADA` policy block, the anti-invent rule, and all tool-usage
guidance. Only `{brand_name}` and `{debtor_name}` are substituted. The agent then has NO
injected policy data, so the entire latency optimization this phase is built around
(inline policy → skip `get_policy_info`) is silently defeated for any tenant using an
override, and the agent is far more likely to hallucinate amounts/dates because the
anti-invent guardrails are gone. The auto-memory note for this phase flags this exact
"override is broken (2000-char cap = 69% truncation)" design as the thing to fix; the code
here still ships the broken full-replace behavior. This is a robustness/correctness gap, not
just a feature miss.
**Fix:** Implement the planned 3-layer composition: keep the hardcoded "motor"/data layers
(policy block, anti-invent rule, tool rules) and only let the tenant override the
personality layer. At minimum, append the policy block to the tenant prompt rather than
discarding it.

### WR-04: `{debtor_name}` / brand substitution is partial and order-dependent — leaks template tokens

**File:** `backend/cobranza/voice_pipecat.py:325-327`
**Issue:** Substitution runs on the **truncated** 2000-char string. If a `{brand_name}` or
`{debtor_name}` placeholder straddles the 2000-char boundary, it is cut in half and a
dangling `{brand_na` is spoken to the debtor. Also only two tokens are supported; any other
`{...}` a tenant writes is read aloud verbatim. There is no validation that substitution
succeeded.
**Fix:** Substitute BEFORE truncating, and strip/validate any remaining `{...}` tokens
(regex `\{[a-z_]+\}`) so stray placeholders never reach TTS.

### WR-05: `formInvalid` not re-checked after async `configure` — password kept in component state after failure

**File:** `frontend/src/components/SoftSegurosSetup.tsx:95-111`
**Issue:** `handleSubmit` reads `formInvalid`/`username`/`password` once at submit time
(fine), but on a failed `configure` (returns falsy) the plaintext `password` remains in
React state indefinitely and is still bound to the password `<input>`. For a credentials-
import flow this is a minor secret-handling smell — the SoftSeguros password lingers in
memory and in the DOM input value across retries. The "failed" branch (line 225) clears it,
but the inline-error branch (`error` shown, still on the form) does not.
**Fix:** On a failed `configure`, clear `password` (and optionally `username`) state, or at
least clear it once the request resolves regardless of outcome.

### WR-06: `etaText` divides by `scanned` rate that can momentarily be 0 → no guard distinguishes "stalled" from "done"

**File:** `frontend/src/components/SoftSegurosSetup.tsx:83-93`
**Issue:** `rate = scanned / elapsedSec` and then `remaining / rate`. The code guards
`rate <= 0` (returns "Calculando…"), but if `total` is briefly reported smaller than
`scanned` (server race during pagination), `remaining = Math.max(0, total - scanned)` is 0
and ETA shows "~0 s restantes" while the bar is < 100%, which reads as a stuck/false-
complete state to the user. Not a crash, but a confusing UX during a 20-40 min import.
**Fix:** When `scanned >= total && total > 0`, render a "Finalizando…" state instead of
"~0 s restantes".

### WR-07: WhatsApp team-notification message built from unsanitized debtor fields

**File:** `backend/cobranza/voice_pipecat.py:817-824`
**Issue:** `msg` interpolates `debtor.get('nombre')`, `telefono`, `numero_poliza`, and the
model-supplied `detalle` directly into a WhatsApp message sent to the team. `detalle` is
LLM-generated free text and `nombre` originates from an external sync. This is low-risk
(WhatsApp text, internal recipient) but it is unbounded in length (a long hallucinated
`detalle` is sent verbatim) and could contain content that breaks downstream parsing if the
team WhatsApp is itself automated.
**Fix:** Truncate `detalle` (e.g. `[:300]`) and the debtor fields before interpolation, as
is already done for log lines (`detalle[:80]`).

## Info

### IN-01: `allowedHosts: true` in Vite dev server disables host-header checking

**File:** `frontend/vite.config.ts:8`
**Issue:** `allowedHosts: true` allows any Host header to reach the dev server, disabling
Vite's DNS-rebinding protection. Acceptable for a tunneled demo (ngrok/Twilio webhook) but
should not ship to any shared/staging environment.
**Fix:** Restrict to the specific tunnel host(s) once known, or gate behind an env flag.

### IN-02: Greeting `random.choice` makes the deterministic "exact greeting" instruction non-deterministic across reconnects

**File:** `backend/cobranza/voice_pipecat.py:615-643`
**Issue:** `first_message` is randomly chosen and then the system prompt demands the model
say it "EXACTAMENTE". On a WebSocket reconnect, `run_bot` runs again and picks a different
greeting, so a reconnected caller may hear two different openings. Cosmetic for a demo.
**Fix:** Seed the choice on `call_sid` so it is stable per call.

### IN-03: Dead/misleading comments — Twilio vs Telnyx, Silero vs Gemini VAD

**File:** `backend/cobranza/voice_pipecat.py:106-117, 330-348`
**Issue:** Docstring says "Telnyx transport" and references `TelnyxFrameSerializer`, but the
code uses `TwilioFrameSerializer`. The transport comment says "Silero VAD here handles user-
speech interruptions" then immediately contradicts itself with "NO Silero VAD here." These
stale comments will mislead the next maintainer debugging audio/turn-taking.
**Fix:** Reconcile comments with the actual Twilio + Gemini-native-VAD implementation.

### IN-04: `inflightRequests` dedup never rejects waiters distinctly; shared promise rejection is fine but cache key ignores body

**File:** `frontend/src/api.ts:91-98, 129-134`
**Issue:** Dedup is GET-only and keyed on `method:endpoint`, which is correct since GETs
carry no body. Minor: if two GETs to the same endpoint race and the first 401s, both
waiters get the same `landa:unauthorized` dispatch — harmless but worth noting. No action
required for the demo.
**Fix:** None required; documented for completeness.

### IN-05: `temperature`/`vad_*` tenant overrides parsed with `or` swallow legitimate 0 values

**File:** `backend/cobranza/voice_pipecat.py:570, 606-607`
**Issue:** `float(tenant_config.get("voice_temperature") or 0.5)` — a tenant explicitly
setting `voice_temperature: 0` (fully deterministic) gets `0.5` instead, because `0 or 0.5`
is `0.5`. Same pattern for `vad_prefix_padding_ms`/`vad_silence_duration_ms` (a configured
`0` is replaced by the default). Probably acceptable defaults, but the override is silently
ignored at the 0 boundary.
**Fix:** Use explicit `None` checks: `cfg.get("voice_temperature") if ... is not None else 0.5`.

---

_Reviewed: 2026-06-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
