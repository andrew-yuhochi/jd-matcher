# Data Sources — jd-matcher (PoC)

> **Author**: architect
> **Date**: 2026-04-24
> **Input**: RESEARCH-REPORT.md (research-analyst, 2026-04-24)
> **Feeds into**: TDD.md §1.1 Data Flow, M1 / M2 / M4 ingestion implementation

This document is structured for implementer use. Per-source feasibility verdicts are inherited from RESEARCH-REPORT.md §2 and not re-derived. When a research-analyst finding is load-bearing, it is referenced inline.

---

## Source coverage by milestone

| Milestone | Sources added | Path |
|-----------|---------------|------|
| M1 | LinkedIn (Gmail), Indeed (Gmail) | A — Gmail email alerts + JD hydration |
| M2 | Himalayas | B — direct API |
| M4 | Job Bank Canada (Gmail), Remotive (API), Jobicy (API), HN HNRSS (RSS) | A + B |

---

## Path A — Gmail email-alert sources

All Gmail sources share infrastructure: a single dedicated Gmail account holds inbound alerts; the Gmail Ingester polls hourly and routes by sender to per-source parsers. OAuth setup happens once.

### Gmail (transport, not a job source)

| Field | Value |
|-------|-------|
| Type | API (transport for closed-platform alerts) |
| Access method | `google-api-python-client` — `users.messages.list` + `users.messages.get` |
| Authentication | OAuth 2.0 — loopback redirect on `http://127.0.0.1:{port}` (RESEARCH-REPORT.md §4); refresh-token reuse |
| Rate limits | 1.2M units/min project-wide; 15K/min per user. `messages.list` = 5 units, `messages.get` = 5 units. Daily limit: none. |
| Cost | Free |
| Availability | Confirmed |
| Update frequency | Polled hourly by the pipeline (DISCOVERY-NOTES.md §9) |
| Expected volume per fetch | <1,000 quota units per run — orders of magnitude below the rate limit |

**OAuth setup (one-time, manual)**:
1. Create GCP project, enable Gmail API.
2. Create OAuth 2.0 client ID — type **Desktop app**.
3. Download `credentials.json`, place at `$GOOGLE_APPLICATION_CREDENTIALS` path.
4. Add user's Google account as a Test User (Cloud Console).
5. First pipeline run opens browser for consent; subsequent runs use the stored refresh token.

**Search query for filtering**: `from:<sender> newer_than:2d` per source. Optional Gmail label routing for the user's organisation.

**Failure mode (Risk 2 / R2)**: refresh token revoked after 90+ days inactivity, app status change, or user revocation. Pipeline halts for Gmail sources only — API sources continue (per-source isolation, TDD §1.5). UX surfaces a persistent banner per UX-SPEC.md §8.

---

### LinkedIn (via Gmail alerts)

| Field | Value |
|-------|-------|
| Purpose in PoC | Highest-volume source for Vancouver / Remote-Canada DS roles. Closed platform — no API path with zero account-ban risk (DISCOVERY-NOTES.md §3). |
| Access method | Gmail API → per-message parser (URL-regex on plain-text part) |
| Sender address | `jobalerts-noreply@linkedin.com` (and historical variants — verified during M1 implementation) |
| Auth / setup | User must create **7 daily saved searches on linkedin.com/jobs** before ingest can produce data (DISCOVERY-NOTES.md §4). Coverage strategy: missing a role is worse than duplicate emails. Seed list: Data Scientist · Senior Data Scientist · Machine Learning Engineer · Applied Scientist · Data Science · Research Scientist · Staff Data Scientist. Vancouver + Remote Canada filters per saved search. Iterative additions deferred to MVP-M2 based on M4 coverage audit. |
| Fields available | Job title, company name, location, **job URL** (most reliable), embedded job ID. Salary unreliable. Short description present in some templates. Posted date absent (only relative time). |
| Fields we extract | `linkedin_job_id` (regex `linkedin.com/jobs/view/(\d+)`) — **primary**. Title, company, location — secondary. Salary — opportunistic. |
| Rate limits | None on the email side (Gmail polling determines cadence). |
| Polling cadence | Hourly Gmail poll. |
| Known limitations | (a) URL-regex is the only stable extractor — HTML/CSS structure changes silently with no changelog (RESEARCH-REPORT.md §3). (b) Gmail rewrites the plain-text part of forwarded emails — never test with forwarded samples (RESEARCH-REPORT.md §3). (c) Parsed title/company are metadata only; canonical title comes from JD hydration + LLM extraction. |
| Fallback | URL-only ingestion if title/company extraction fails. Posting still flows through the rest of the pipeline (hydration recovers the JD). Health metric "URL-only fraction" alerts at >20%. |

**Parsing strategy** (per RESEARCH-REPORT.md §3 and DISCOVERY-NOTES.md §3):
1. Fetch raw RFC-822 via `messages.get(format='raw')`.
2. Decode + extract `text/plain` part.
3. Apply regex `linkedin.com/jobs/view/(\d+)` over the entire decoded body — collect all job IDs.
4. Optionally extract title/company/location heuristically (template-aware best-effort).
5. Store the raw email body in `postings_sources.raw_payload` for replay against future template changes.
6. Each unique job ID becomes a row in `postings_sources` (one source instance) → JD Hydrator processes it once.

---

### Indeed.ca (via Gmail alerts)

| Field | Value |
|-------|-------|
| Purpose in PoC | Second-highest coverage for Canada. Indeed Publisher API was deprecated in 2023 (RESEARCH-REPORT.md §6) — email alerts are the only zero-risk path. |
| Access method | Gmail API → per-message parser (URL-regex + HTML parse) |
| Sender address | `alert@indeed.com` (and historical variants — verified during M1 implementation) |
| Auth / setup | User must create **2–3 daily saved searches on indeed.ca** with Vancouver + Remote-Canada filters (DISCOVERY-NOTES.md §3). |
| Fields available | Title, company, location, URL, salary (partial). |
| Fields we extract | Indeed posting URL (canonical permalink), title, company, location, salary if present. |
| Rate limits | None on the email side. |
| Polling cadence | Hourly Gmail poll (shared with LinkedIn). |
| Known limitations | Indeed rewrites links via tracking redirectors — final canonical URL must be resolved (single HEAD request through the redirect chain, gated by the same 1 req / 30s rate limit if it touches `indeed.com` directly). |
| Fallback | URL-only ingestion if other fields fail. |

---

### Job Bank Canada (via Gmail alerts) — M4

| Field | Value |
|-------|-------|
| Purpose in PoC | **Highest-differentiation source** (MARKET-ANALYSIS.md §"PoC/MVP Implications" #2) — every employer is validated as Canadian-eligible-to-hire, directly addressing the OWP work-permit filter. No competitor surfaces this signal. |
| Access method | Gmail API → per-message parser. **No public RSS or search API exists** (RESEARCH-REPORT.md §1) — bulk CSV/Atom is monthly, too stale. Email alerts are the only live path. |
| Sender address | Verified during M4 implementation — Job Bank uses `noreply@jobbank.gc.ca` family. |
| Auth / setup | User must create job alerts on **jobbank.gc.ca** (Vancouver + Remote-Canada + DS/ML keywords) before ingest can produce data. |
| Fields available | Title, employer, NOC code, location. |
| Fields we extract | URL, title, employer, NOC code, location. |
| Rate limits | None on email side. |
| Polling cadence | Hourly Gmail poll (shared). |
| Known limitations | Government IT cycles change templates without notice (Risk 3 / R5 / Risk 3 in RESEARCH-REPORT.md §8). Built last in PoC (M4) so the email-parsing infrastructure is mature. Quality bar: ≥90% URL extraction on ≥10 real samples (lower than LinkedIn/Indeed deterministic bar — accepted fragility). |
| Fallback | Documented fallback to direct scrape of public `jobbank.gc.ca/jobsearch/` results — government public resource, low-risk at personal volume (RESEARCH-REPORT.md §8 Risk 3). Fallback implementation deferred to MVP if email parser falls below 90%. |

---

## Path B — Direct API sources

No Gmail involvement; structured JSON / RSS fetched directly. Strictly better data than email parsing where available.

### Himalayas — M2

| Field | Value |
|-------|-------|
| Purpose in PoC | Highest-quality structured API for Canadian DS/ML — 17 structured fields, no auth, ~93 live Canadian DS results confirmed (RESEARCH-REPORT.md §5, Appendix). |
| Access method | `httpx` GET → `https://himalayas.app/jobs/api/search` |
| Endpoint | `https://himalayas.app/jobs/api/search?q=data+scientist&country=canada&limit=50` |
| Auth / setup | None |
| Fields available | `title`, `companyName`, `seniority` (list), `employment_type`, `country`, `locationRestrictions`, `categories`, `minSalary`, `maxSalary`, `pubDate`, `applyUrl`, plus 6 more |
| Fields we extract | All — fed directly into the URL-seen check then to LLM extraction. Most fields are pre-extracted, so LLM extraction primarily computes `fit_score` + tags + `role_summary`. |
| Rate limits | Triggers HTTP 429 (no documented quota); contact for higher limits |
| Polling cadence | Daily |
| Known limitations | Data refreshes every 24h — back-to-back polls within a day return identical data |
| Fallback | Skip source for the run on persistent 429 / 5xx; surface in `pipeline_runs` and amber-state UI sub-bar |

**Sample response**:
```json
{
  "title": "Sr. Data Scientist",
  "companyName": "Instacart",
  "locationRestrictions": ["Canada"],
  "seniority": ["Senior"],
  "minSalary": 161000,
  "maxSalary": 202500
}
```

---

### Remotive — M4

| Field | Value |
|-------|-------|
| Purpose in PoC | Catch remote-first AI/ML roles that Himalayas misses |
| Access method | `httpx` GET → `https://remotive.com/api/remote-jobs` |
| Endpoint | `https://remotive.com/api/remote-jobs?category=ai-ml` (category id 37 confirmed; `data` slug = id 24) |
| Auth / setup | None |
| Fields available | `title`, `company_name`, `category`, `salary`, `candidate_required_location`, `publication_date`, `url`, `description` |
| Fields we extract | All. Post-fetch filter: `candidate_required_location` includes "Canada" or "Worldwide" |
| Rate limits | Max 2x / minute; recommended 4x / day |
| Polling cadence | Daily |
| Known limitations | "Data Analysis" category yielded mixed-quality results in research; "AI / ML" is the higher-signal category for this user |
| Fallback | Skip source on failure |

---

### Jobicy — M4

| Field | Value |
|-------|-------|
| Purpose in PoC | Zero-marginal-cost addition; thin Canadian DS coverage but may improve |
| Access method | `httpx` GET → `https://jobicy.com/api/v2/remote-jobs` |
| Endpoint | `https://jobicy.com/api/v2/remote-jobs?count=50&geo=canada&industry=data-science` |
| Auth / setup | None |
| Fields available | `jobTitle`, `companyName`, `jobGeo`, `jobLevel`, `jobType`, `salary` (text), `pubDate`, `url`, `jobDescription` |
| Fields we extract | All |
| Rate limits | Not documented |
| Polling cadence | Daily |
| Known limitations | 2 results for `industry=data-science&geo=canada` at research time — coverage is thin |
| Fallback | Skip source on failure |

---

### HN "Who is Hiring" (via HNRSS) — M4

| Field | Value |
|-------|-------|
| Purpose in PoC | Low-volume, high-signal — startups and serious tech companies post here |
| Access method | `feedparser` → `https://hnrss.org/whoishiring/jobs?q=...` |
| Endpoint | `https://hnrss.org/whoishiring/jobs?q=data+scientist+Canada` (or broad `?q=data+scientist`, post-filter for Canada/remote) |
| Auth / setup | None |
| Fields available | Free-text comment, item link, `pubDate` |
| Fields we extract | Job text → regex parse for company, role, location, remote flag, apply URL. Free-text dump preserved as `raw_payload` for LLM extraction to canonicalise. |
| Rate limits | None documented |
| Polling cadence | Weekly (matches HN monthly thread cadence) |
| Known limitations | (a) Job posts follow informal conventions, not a fixed schema — LLM extraction does the heavy lifting. (b) HN HNRSS occasionally returns 502 (research observed during testing) — retry once and skip on persistent failure. |
| Fallback | Skip source on failure |

---

## LinkedIn JD Hydration

This is the **critical design** of the closed-platform path. Documented separately because it has the highest risk profile and the most explicit ToS posture.

### What it is

For each newly-extracted LinkedIn job URL (once per `seen_urls`, ever), fetch the public **logged-out guest endpoint** to retrieve the full JD. Used because LinkedIn alert emails contain only a short teaser, but full JDs are required for: user decision-making, CV-recommender input, content-based dedup, technical-focus classification (DISCOVERY-NOTES.md §3).

### Endpoint

```
GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jobId}
```

- `{jobId}` parsed from the `linkedin.com/jobs/view/(\d+)` regex.
- No authentication. No login. No cookie. Public guest endpoint.
- Equivalent guest endpoint exists for Indeed posting pages.

### Rate limit

**Hard ceiling: 1 request per 30 seconds** across all hydration calls (LinkedIn + Indeed combined). Baked into the `JD Hydrator` component (TDD §1.2). At ~40 unique URLs per day, this is well within the 30-second budget across the daily run window.

### Parse strategy

1. **URL regex (primary)** — `linkedin.com/jobs/view/(\d+)` extracts `jobId` from the email body deterministically. This is the canonical identifier and is stable across email template changes (RESEARCH-REPORT.md §3).
2. **HTML parse (secondary)** — once hydrated, parse the response with `selectolax` (fallback `beautifulsoup4`) to extract the full JD text. Reuses JD-extraction code from `py-linkedin-jobs-scraper` (vendored / referenced — **only the JD-parsing helpers, never the list/search methods** — DISCOVERY-NOTES.md §3).

### ToS posture (on the record)

LinkedIn's Terms of Service broadly prohibit automation. The guest-endpoint approach is technically ToS-gray. At single-user personal volume (~40 requests/day, no authentication, no cookie, no login), enforcement risk is very low. **The trade-off was presented to the user during discovery and explicitly accepted (DISCOVERY-NOTES.md §3).**

This approach **does not scale commercially**. The HiQ Labs precedent (HiQ v. LinkedIn, 2022 settlement — MARKET-ANALYSIS.md Risk 1) means a commercial pivot requires a different LinkedIn ingestion layer (email-only at scale or paid aggregator like SerpAPI / a licensed feed). No PoC architectural choice solves this. Documented here so the constraint is auditable.

### Failure modes

| Scenario | Tier | Behaviour |
|----------|------|-----------|
| Single 429 / timeout | Minor | Backoff (start 60s) + retry once; skip URL for this run on persistent failure |
| Sustained 429 across the run | Major | Halt hydration for the run; URLs remain in `postings_sources` with `raw_payload` (email teaser) so cards still render with reduced data |
| HTML structure change breaks parser | Major | Parser writes the raw HTML to disk for replay; URL + email-teaser remain stored. Auto-fix attempts up to 3, root-cause first. |
| LinkedIn detects + IP-blocks | Directional | Halt all hydration; surface to user immediately. No auto-retry. User decides next ingestion approach (e.g. shift LinkedIn to email-only mode). |

---

## Deferred sources (not in PoC)

Inherited from DISCOVERY-NOTES.md §3, RESEARCH-REPORT.md §2, and ROADMAP.md §"Out of scope (PoC)". Per-source reason for deferral.

| Source | Reason for deferral | Possible re-evaluation |
|--------|---------------------|------------------------|
| **Monster Canada** | Coverage too thin for Canadian DS/ML to justify engineering effort | Permanently out unless coverage signal changes |
| **Wellfound (AngelList)** | No official API path; weak Canadian employer coverage; startup-skew = US-skew | Out of PoC; revisit only if a startup-specific need surfaces |
| **Google for Jobs** | No free RSS/email path. SerpAPI free tier (~250 / mo) is borderline; paid tier ($25 / mo) breaks the PoC LLM budget | Revisit at MVP if M4 coverage audit shows a gap |
| **aijobs.net** | RSS / per-alert RSS behind $17 / mo paywall | Revisit at MVP only if budget is allocated and gap surfaces |
| **Greenhouse ATS API** | Free + structured but requires a curated list of 20–30 Canadian-employer slugs (~1 hr initial curation + ongoing maintenance). User declined the curation overhead for PoC (DISCOVERY-NOTES.md §3) | MVP-M2 if M4 coverage audit indicates a clear gap (RESEARCH-REPORT.md §5; ROADMAP.md MVP-M2) |
| **Lever ATS API** | Same as Greenhouse + slug discovery is unpredictable per employer (RESEARCH-REPORT.md §5) — higher friction than Greenhouse | MVP-M2 alongside Greenhouse, only if the gap warrants both |
| **Direct company career pages** | Per-site scraping maintenance cost — every site is bespoke | Permanently deferred unless a high-value employer is uniquely missed |
| **Vancouver Tech Journal Jobs Board** | No confirmed RSS / API at research time | Bookmark for manual monitoring; revisit if RSS surfaces |
| **BCtechjobs.ca** | API URL not confirmed at research time | Confirm at MVP-M2 if discovered |

---

## Data quality considerations

- **LinkedIn**: title/company unreliable as canonical — use them as metadata only; canonical title comes from JD hydration + LLM extraction (DISCOVERY-NOTES.md §5 Stage 0).
- **Indeed**: tracking-redirector URLs require a HEAD-resolution step before storage.
- **Job Bank**: government template volatility — store raw email bodies for replay (Risk 3 mitigation).
- **HN**: free-text — LLM extraction is mandatory for canonicalisation. Lower expected accuracy on `salary_min/max_cad` for HN than for structured APIs.
- **All sources**: salary fields are optional and frequently missing. UI renders "Salary not listed" in muted italic (UX-SPEC.md §3) — never silently drop.
- **All sources**: Pydantic validation at every external API boundary. Unexpected schema → log WARNING, abort that source's run (TDD §1.5). Never silently accept malformed data.

---

## Data privacy & compliance

- **No PII processed beyond what is in the user's own Gmail account.** Postings are public job listings.
- **No commercial processing of third-party PII** — out of PIPEDA scope.
- **CV files** referenced by filesystem path; `parsed_text` and `embedding` stored locally in SQLite. Never transmitted to third parties beyond the embedding API call (OpenAI).
- **OpenAI API**: full-JD text is sent for extraction + embedding. JDs are public; no privacy concern. CV `parsed_text` is sent to the embeddings endpoint at startup — user's own document, sent under their own API key, governed by OpenAI's data-use policy (no training on API data by default).

---

## Fallback strategy summary

| Source | At-risk? | Fallback |
|--------|----------|---------|
| Gmail (transport) | Yes — refresh-token revocation | Surface persistent banner + `[Reconnect Gmail]`; API sources continue |
| LinkedIn (email) | Yes — template change | URL-only fallback; raw email replay; health metric on URL-only fraction |
| Indeed (email) | Yes — template change | URL-only fallback; raw email replay |
| Job Bank (email) | Yes (Risk 3) | Documented fallback to public-page scrape (deferred to MVP) |
| LinkedIn / Indeed JD hydration | Yes — rate-limit / IP-block | Store URL + email teaser; render card with reduced data; banner if sustained |
| Himalayas | No (free, stable) | Skip source on failure |
| Remotive | No | Skip source on failure |
| Jobicy | No | Skip source on failure |
| HN HNRSS | No | Skip source on failure |
| OpenAI (extraction + embeddings) | Yes — outage / quota / key revocation | Cards persist with `extraction_status='failed'`; can be re-run when API recovers. Local Ollama + sentence-transformers config-swap remains an opt-in user fallback. |

Per-source isolation is enforced at the pipeline orchestrator level (TDD §1.5) — one source's failure never cascades.

---

## Manual setup checklist

User actions required before the M1 pipeline can run end-to-end. Becomes part of M1 task scope (documented in README + onboarding instructions). **Order matters.**

1. **Create or designate a dedicated Gmail account** for job alerts (DISCOVERY-NOTES.md §3 — one already exists for the user). All alert subscriptions are routed here.
2. **Create OpenAI API key** with usage limits set ($5/mo cap for safety). Place in `.env` as `OPENAI_API_KEY`.
3. **GCP / Gmail API setup**:
   - Create a GCP project; enable the Gmail API.
   - Create an OAuth 2.0 client ID — type **Desktop app**.
   - Download `credentials.json` and place at `~/.jd-matcher/credentials.json`.
   - Add the dedicated Gmail address as a **Test User** (Cloud Console → OAuth consent screen).
4. **Create 7 LinkedIn saved searches** (DISCOVERY-NOTES.md §4) — Vancouver + Remote-Canada per search:
   - Data Scientist
   - Senior Data Scientist
   - Machine Learning Engineer
   - Applied Scientist
   - Data Science
   - Research Scientist
   - Staff Data Scientist
   Set each to **daily** alert delivery.
5. **Create 2–3 Indeed.ca saved searches** (DISCOVERY-NOTES.md §3) with Vancouver + Remote-Canada filters and DS/ML keywords. Set each to daily delivery.
6. **Create Job Bank Canada job alerts** at **jobbank.gc.ca** — Vancouver + Remote-Canada + DS/ML keywords. (Required before M4; not blocking for M1.)
7. **Set up an optional Gmail label** for routing alerts — recommended UX (RESEARCH-REPORT.md §4) but not required.
8. **Place 5 CV variant PDFs** on the local filesystem and note their paths. (Required before M4; not blocking for M1.)
9. **Run `python auth.py`** once — opens browser for Gmail OAuth consent; stores refresh token at `~/.jd-matcher/tokens.json`.
10. **Run `python -m jd_matcher.pipeline`** once to verify Gmail → email parser → JD hydrator → SQLite end-to-end.

Onboarding is single-user, documentation-first. No installer, no setup wizard in PoC.
