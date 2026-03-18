# Feature Research

**Domain:** AaaS (Agents as a Service) B2B Sales Prospecting Platform — Visual Agent Office UI
**Researched:** 2026-03-17
**Confidence:** MEDIUM (training data + thorough project context; WebSearch unavailable)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features clients assume exist. Missing these = platform feels unfinished or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Campaign variable configuration form (10 vars)** | Client must tell the agent who they are and what to sell before any run — this IS the product setup | MEDIUM | nombre_remitente, empresa_remitente, industria_objetivo, ciudad_objetivo, dolor_operativo, solucion_ofrecida, software_clave, jerarquia_decisores, identidad_remitente, contenido_scrapeado (dynamic). Form must validate required fields before allowing run launch. |
| **URL input → run trigger** | The primary action: give a company URL, get a lead decision. Must be a single clear CTA in the UI | LOW | POST to pipeline endpoint. The "start prospecting" button must be prominent and obvious. |
| **Real-time agent state visibility** | Clients paying for an AaaS platform need to see that work is actually happening — else they don't trust it | MEDIUM | Already exists via WebSocket. Needs to show current node (sourcing/scoring/veto/email). State labels: THINKING, TOOL_USE, WAITING, HITL_PENDING. |
| **Lead outcome display (approved vs rejected)** | After a run, clients must see the result immediately. Rejected = why. Approved = the expediente | MEDIUM | Two outcomes: REJECTION_PAYLOAD (with kill switch code) or SUCCESS expediente. Both must render visibly. |
| **Expediente viewer** | The deliverable is a Markdown expediente + JSON. Clients expect to read it in the UI, not download raw text | MEDIUM | Render Markdown expediente in-panel. Show score, decisor, trigger, email draft. Side-by-side or tabbed Markdown/JSON. |
| **Email draft display with copy** | The A/B subject lines and email body are the monetizable output. Must be readable and copyable in one click | LOW | Pre-formatted email block with "Copy to clipboard" per section. Not a send button — just copy. |
| **Run history / lead log** | Clients run batches over time. They expect to see all past leads, not just the current one | MEDIUM | Per-user run log: company URL, score, outcome, timestamp. Clickable to re-open expediente. |
| **Score display with breakdown** | AaaS users want to trust the agent's judgment. Showing score (0-100) + which criteria fired justifies the decision | LOW | Score badge on each lead card. Expandable score breakdown: base B2B +20, tension +X, escala +X, decision +X, geo +X. |
| **Session auth (login)** | Multi-tenant platform — users expect their leads and configuration to be private and persistent | MEDIUM | Email/password minimum. JWT or session cookie. Each user sees only their own runs and agents. |
| **Per-user agent isolation** | Users expect their campaign config to not bleed into other clients' runs | MEDIUM | Scoped by user_id on all DB queries. Agent config stored per user. Run state isolated. |

### Differentiators (Competitive Advantage)

Features that set this platform apart. The pixel art office is the primary differentiator — everything else should reinforce that metaphor.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Pixel art office as primary UI** | Competitors (Clay, Apollo, Hunter) use tables and dashboards. This makes the AI work *feel* alive and tangible. Creates emotional connection with the product. | HIGH (exists already) | Office canvas is already built. Differentiator is maintained by NOT replacing it with a generic dashboard. Every new feature should be surfaced through the office metaphor first. |
| **HITL pause in the office (visual freeze)** | When the agent reaches human_review node, the character in the office visually pauses and waits. The approval/rejection flow happens *inside the office*, not in an email or external panel. Creates a unique handoff moment. | HIGH | Agent character enters a HITL_PENDING state with visual indicator (flashing, speech bubble asking for review). Approve/Reject buttons appear contextually near the agent sprite. This is the UX that no competitor has. |
| **Click-on-agent to see configuration** | Users can click any office character and see their full personality: name, role, system prompt modules, campaign variables. Makes the "black box" transparent. Builds trust in the agent's behavior. | MEDIUM | Agent detail panel slides in on character click. Shows: identity, active modules (sourcing, kill switches, scoring, expediente), current campaign variable values. Read-only for now. |
| **Kill switch transparency (why rejected)** | Most automation tools give vague rejection reasons. This platform shows exactly which kill switch fired (KILL_B2C, KILL_ZOMBIE_COMPANY, etc.) and the evidence phrase that triggered it. | LOW | Already in REJECTION_PAYLOAD. Display the kill switch code + evidencia_encontrada in the lead card. Clients learn to calibrate expectations from these rejections. |
| **Score breakdown with reasoning** | Showing the exact scoring logic (not just a number) teaches clients how the agent thinks and builds trust. Competitors give a "fit score" with no explanation. | LOW | Render the 5 scoring criteria as a mini scorecard: which fired, how many points each. Sourced directly from scoring_node output. |
| **Agent character animations tied to pipeline nodes** | Each graph node (sourcing, scraping, scoring, email composing) maps to a distinct character animation state. Users can literally watch what the agent is doing at each step. | MEDIUM | Requires mapping GraphExecutor node events → frontend animation states. sourcing_node → THINKING, tool execution → TOOL_USE, hitl → WAITING, etc. |
| **Campaign variable template library** | Clients running multiple campaigns (clinicas, software, logistica) want to save and reuse their 10-variable configs. Reduces friction for repeat runs. | MEDIUM | Save named templates per user. "Clone template" action. Not full agent editor — just variable preset storage. |
| **Rejection analytics panel** | Shows which kill switches fire most often for a given campaign config, helping clients understand if their targeting is off. No competitor surfaces this. | MEDIUM | Aggregate rejection codes per user per campaign config. Bar chart: "67% KILL_LOW_VOLUME — consider adjusting industria_objetivo." |

### Anti-Features (Deliberately NOT Building in v1)

Features that seem useful but add scope/risk/complexity disproportionate to v1 value.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Direct email sending (SendGrid integration)** | "Can the agent send the email automatically?" is the first question clients ask | Email deliverability requires domain warm-up, SPF/DKIM/DMARC setup, bounce handling, unsubscribe management, CAN-SPAM compliance. Building this badly destroys sender reputation and can blacklist the client's domain permanently. Legal liability in Colombia (Ley 1581). | Copy-to-clipboard on the email draft. Let the client send from their own warmed domain. Label it clearly as a "v2 feature after deliverability setup." |
| **CRM push (HubSpot/Salesforce)** | Clients want leads to appear automatically in their CRM | OAuth flows, field mapping per CRM, webhook error handling, API rate limits, schema mismatches per client. Each CRM integration is a mini-product. Breaks easily, hard to debug. | Export expediente as JSON. Client pastes/imports manually. v2 scope with dedicated CRM connector feature. |
| **LinkedIn scraping** | Decisor data enrichment | ToS violations with LinkedIn. Anti-scraping measures break regularly. Legal risk (CFAA in US, similar in Colombia). Firecrawl/Apify approaches get rate-limited. | Use web_scrape_tool on company website only. Decision maker extraction from public web pages is legally safer. LinkedIn as fallback reference only (no automated scraping). |
| **Multi-agent batch processing (queue 50 URLs)** | "Can I paste a list of 50 URLs and run them all?" | LLM cost per run is significant. Rate limiting on web_scrape_tool. No cost controls in v1. A bug in batch processing could trigger hundreds of expensive API calls. Race conditions in WebSocket state updates for multiple concurrent runs. | Single-URL runs in v1. Validate pipeline cost and reliability first. Batch as v1.x after stable single-run. |
| **Agent builder UI (natural language agent creation)** | "Can I create my own custom agent?" | The Hive BuildSession is powerful but complex. Exposing it to non-technical users requires significant UI/UX work and safety guardrails. Scope creep risk. Clients don't need to build agents — they need prospecting results. | Hard-code the prospector_b2b agent for v1. Variables configuration IS the customization clients need. Full agent builder as v2+ premium tier. |
| **Self-improving graph evolution** | "Can the agent learn from rejections and improve?" | Hive supports self-improving graphs (Goal → Evolve cycle) but automated prompt mutation in production is risky — a bad evolution step could corrupt the prospecting logic silently. Requires robust evaluation harness before enabling. | Manual prompt calibration by the platform operator (weekly ritual). Operator reviews rejection patterns and tunes personalidad.md. Automated evolution as v2 after evaluation framework is built. |
| **Slack/Teams notifications** | "Notify me when a lead is ready" | OAuth flows for workspace installs, webhook management, notification fatigue design. Adds infra complexity for something that can be solved by polling the leads dashboard. | In-browser notification (browser Notification API) when HITL review is ready. Email notification as v1.x. Slack as v2. |
| **Mobile app** | Accessibility on the go | The pixel art office experience requires a decent-sized screen. Canvas-based UI on mobile is degraded. Touch interactions for HITL approvals are error-prone. High build cost for low v1 value. | Ensure the web app is usable at tablet width as minimum viable mobile experience. Native app deferred indefinitely. |
| **White-label / reseller mode** | Agency clients want to rebrand the platform for their own customers | Requires theming system, custom domains, isolated billing, separate admin panels per reseller. Enormous scope. | Single-brand v1. Revisit if agencies become primary customer segment. |
| **Lead enrichment API calls (Clay, Apollo)** | "Can the agent enrich leads with more data?" | Each enrichment API is a cost center. Clay pricing is credit-based and expensive at scale. Adds external dependencies that can fail. Enrichment data quality is uneven for Colombian market. | The agent already extracts tech stack, decisor, and infraestructura from the company website. That IS enrichment. Clay as v2 optional add-on. |

---

## Feature Dependencies

```
[Auth / Multi-tenant isolation]
    └──required by──> [Campaign variable config form]
                          └──required by──> [Run trigger (URL input)]
                                                └──required by──> [Real-time agent state]
                                                                      └──required by──> [HITL pause in office]
                                                                      └──required by──> [Expediente viewer]
                                                                                            └──required by──> [Run history / lead log]

[Agent character animations]
    └──enhances──> [Real-time agent state visibility]
    └──enhances──> [HITL pause in office]

[Score breakdown display]
    └──enhances──> [Expediente viewer]
    └──enhances──> [Kill switch transparency]

[Campaign variable template library]
    └──requires──> [Campaign variable config form]

[Rejection analytics panel]
    └──requires──> [Run history / lead log]
    └──requires──> [Kill switch transparency]

[Click-on-agent config view]
    └──enhances──> [Agent character animations]
    └──requires──> [Campaign variable config form] (to display current values)
```

### Dependency Notes

- **Auth requires before everything:** User isolation must exist before any data is persisted. No auth = all clients share a global state — catastrophic for a multi-tenant AaaS.
- **Campaign config requires Auth:** Config is per-user. Without auth, there is no "per-user" config to store.
- **Run trigger requires Campaign config:** The agent cannot run without the 10 campaign variables being set. The pipeline substitutes `{{industria_objetivo}}`, `{{dolor_operativo}}` etc. at runtime. Empty variables = broken prompts.
- **HITL pause requires Real-time state:** HITL is a state (HITL_PENDING) in the agent lifecycle. The WebSocket broadcast must include this state for the frontend to render the pause correctly.
- **Expediente viewer requires Run trigger:** The expediente is the output of a successful run. No runs = no expedientes.
- **Rejection analytics requires run history:** Analytics are aggregated from historical run records. Must have ≥5-10 runs to be meaningful.
- **Campaign template library enhances but does not block:** This is a convenience feature. Run history and the config form work without it.

---

## MVP Definition

### Launch With (v1)

Minimum viable to demonstrate one client pilot completing a full prospecting run.

- [ ] **Auth (login/session)** — Without this, no multi-tenant isolation, cannot demo to real client
- [ ] **Campaign variable config form** — The 10 variables are the product's primary input interface
- [ ] **URL input + run trigger** — The core user action: give a company, get a verdict
- [ ] **Real-time agent state via WebSocket** — Client must see the agent working, else the pixel office has no purpose
- [ ] **HITL pause in the office** — The approval moment is the signature UX of this product; must be in v1
- [ ] **Expediente viewer (Markdown + score)** — The deliverable must render in-app, readable
- [ ] **Email draft with copy** — Primary reason clients pay: get a ready-to-send personalized email
- [ ] **Kill switch rejection display** — Clients need to see rejected leads too, with reason, to trust the filter
- [ ] **Run history (lead log)** — At minimum a list of past runs per user with outcome and score
- [ ] **Click-on-agent config view** — Demonstrates transparency and differentiates from black-box competitors

### Add After Validation (v1.x)

Features to add once first client pilot is running and providing feedback.

- [ ] **Score breakdown UI** — Trigger: clients ask "why 72 points?" more than once
- [ ] **Campaign variable template library** — Trigger: client runs more than 3 different campaign configurations
- [ ] **Rejection analytics panel** — Trigger: client has >20 runs and asks "why do so many get rejected?"
- [ ] **In-browser notification for HITL ready** — Trigger: client complains about not knowing when to review
- [ ] **Batch run (up to 5 URLs)** — Trigger: stable single-run pipeline with no errors for 2 weeks

### Future Consideration (v2+)

Defer until product-market fit is established and first paying customers exist.

- [ ] **CRM push (HubSpot/Salesforce)** — Defer: integration complexity high, client can paste JSON manually for now
- [ ] **Email sending (SendGrid)** — Defer: deliverability setup is a product in itself
- [ ] **Slack/Teams notifications** — Defer: browser notifications sufficient for v1 cadence
- [ ] **Agent builder UI** — Defer: clients need prospecting results, not agent construction tools
- [ ] **Self-improving graph evolution** — Defer: requires evaluation harness that doesn't exist yet
- [ ] **Clay/enrichment API** — Defer: website scraping is sufficient for Colombian market B2B
- [ ] **White-label / reseller mode** — Defer: validate single-brand first

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Auth / session | HIGH | MEDIUM | P1 |
| Campaign variable config form | HIGH | MEDIUM | P1 |
| URL input + run trigger | HIGH | LOW | P1 |
| Real-time agent state (WebSocket) | HIGH | LOW (exists) | P1 |
| HITL pause in office | HIGH | HIGH | P1 |
| Expediente viewer | HIGH | MEDIUM | P1 |
| Email draft + copy | HIGH | LOW | P1 |
| Kill switch rejection display | MEDIUM | LOW | P1 |
| Run history / lead log | MEDIUM | MEDIUM | P1 |
| Click-on-agent config view | MEDIUM | MEDIUM | P1 |
| Score breakdown UI | MEDIUM | LOW | P2 |
| Campaign template library | MEDIUM | MEDIUM | P2 |
| Agent character animations (per node) | HIGH | MEDIUM | P2 |
| Rejection analytics panel | LOW | MEDIUM | P2 |
| In-browser HITL notification | MEDIUM | LOW | P2 |
| Batch run (5 URLs) | MEDIUM | HIGH | P3 |
| CRM push | MEDIUM | HIGH | P3 |
| Email sending | HIGH | HIGH | P3 |
| Agent builder UI | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch — cannot demo to a client pilot without these
- P2: Should have — add in first iteration after pilot feedback
- P3: Nice to have — future consideration post product-market fit

---

## Competitor Feature Analysis

| Feature | Apollo.io | Clay | Hunter.io | Our Approach |
|---------|-----------|------|-----------|--------------|
| Lead database UI | Table/list view with filters | Spreadsheet grid | Email finder form | Pixel art office — agents as characters, not rows |
| Agent configuration | None (static enrichment) | Column formulas | None | 10-variable form that feeds a real agent system prompt |
| Real-time execution visibility | None — async background | None — async enrichment | None | Live WebSocket agent states in pixel office |
| Lead qualification logic | Rule-based filters | Waterfall enrichment | None | 7 kill switches + 5-criterion scoring, transparent per lead |
| HITL review | None — fully automated | None | None | Pause in the office — character waits for human decision |
| Expediente output | CSV export | Row export | Email export | Markdown expediente + JSON + personalized email draft |
| Multi-tenant isolation | Yes (standard SaaS) | Yes (standard SaaS) | Yes (standard SaaS) | Yes (user-scoped runs and configs) |
| Market focus | Global (English-first) | Global (English-first) | Global | Colombia B2B — Spanish-language prompts, geo scoring |

**Observation (MEDIUM confidence, from training data):** The primary gap in existing tools is transparency of reasoning and experiential engagement. Apollo, Clay, and Hunter treat prospecting as data manipulation. This platform treats it as a witnessed process — the client watches an agent think, filter, and decide. That is the product's core differentiation and must be protected at every design decision.

---

## Sources

- Project context: `personalidad.md` — 4-module agent system prompt with exact kill switch logic, scoring criteria, expediente schema (HIGH confidence — primary source)
- Project context: `negocio.md` — Hive framework architecture, node graph design, 10 campaign variables, HITL node placement (HIGH confidence — primary source)
- Project context: `PROJECT.md` — Validated requirements, out-of-scope items, key decisions (HIGH confidence — primary source)
- Competitor knowledge: Apollo.io, Clay, Hunter.io feature sets from training data (MEDIUM confidence — may be outdated, verify current pricing/features before competitive claims)
- AaaS pattern knowledge: HITL design, multi-tenant isolation, WebSocket state patterns — training data (MEDIUM confidence)
- B2B email compliance (Colombia Ley 1581, CAN-SPAM) — training data (MEDIUM confidence — verify with legal before v2 email send feature)

---

*Feature research for: Hive Pixel Office — AaaS B2B Prospecting Platform*
*Researched: 2026-03-17*
