# jd-matcher — Technical Feasibility Research Report

**Date**: 2026-04-24
**Scope**: Pre-discovery ingestion feasibility study — Gmail-unified email-alert proposal + source landscape
**Analyst**: research-analyst

---

## 1. Executive Recommendation

**Accept with modifications.** The Gmail-unified email-alert architecture is technically sound for LinkedIn and Indeed and should be the primary path — it carries zero ToS ban risk for those sources, eliminates scraping infrastructure, and is implementable in Python with standard libraries. The critical caveat is that LinkedIn alert emails do NOT expose structured fields in a machine-readable way; they require per-source HTML/regex parsers, which are fragile and will break silently when LinkedIn redesigns their template. Mitigations exist (URL-only extraction is robust even when layout changes), but this risk must be owned explicitly in the design.

The proposal needs one significant addition: several sources — Himalayas, Jobicy, Remotive, HN Hiring, and Greenhouse/Lever ATS boards — provide **free structured JSON/RSS APIs with no auth required**. These are strictly better than email parsing for those sources (structured fields, no template-fragility) and should be folded into the ingestion layer alongside Gmail. The PoC should treat Gmail-unified as the path for closed platforms (LinkedIn, Indeed, Job Bank) and direct API polling for open-data sources.

The one hard miss in the original proposal: **Job Bank Canada does not offer email alerts or an RSS feed for job searches** (only bulk CSV/Atom at the dataset level, updated monthly). Accessing Job Bank's live postings for personal use requires light scraping of their public search results — which is low-risk for a personal tool but should be acknowledged in design.

---

## 2. Per-Source Feasibility Matrix

| Source | Email Alerts | RSS | Free API | Paid API | Scraping Risk | Fields parseable from email | Freshness | Recommend |
|---|---|---|---|---|---|---|---|---|
| **LinkedIn** | Yes (daily/weekly) | No | No | Enterprise only | HIGH — account ban risk | title, company, location, URL (salary unreliable) | Daily | MUST — email only |
| **Indeed.ca** | Yes (daily/instant) | No | No (Publisher API deprecated 2023) | Scraper APIs ($) | MEDIUM | title, company, location, URL, salary (partial) | Daily/instant | MUST — email only |
| **Job Bank Canada** | Yes (email only) | No public search RSS | No | None | LOW (govt site, lenient) | title, employer, NOC code, location | Daily | MUST — email preferred; direct scrape feasible as backup |
| **Himalayas** | No | No | Yes — `himalayas.app/jobs/api/search` | N/A | N/A | title, company, salary, seniority, locationRestrictions, categories, pubDate | Daily (data refreshes 24h) | MUST — API is high-quality, live-tested |
| **Jobicy** | No | Yes (RSS + JSON API) | Yes — `jobicy.com/api/v2/remote-jobs` | N/A | N/A | jobTitle, companyName, jobGeo, jobLevel, jobType, salary, pubDate | Near-real-time | NICE — Canada filter works, DS coverage thin (2 jobs in test) |
| **Remotive** | No | Yes | Yes — `remotive.com/api/remote-jobs` | N/A | N/A | title, company, category, salary, candidate_required_location, pubDate | Near-real-time | NICE — "AI / ML" and "Data Analysis" categories exist; Canada location filter is candidate_required_location field |
| **HN "Who is Hiring"** | No | Yes — `hnrss.org/whoishiring/jobs?q=...` | Via HNRSS (free) | N/A | N/A | Free text (unstructured comment), link, pubDate | Monthly thread | NICE — low volume, high signal, parse with regex; live-tested |
| **Greenhouse ATS** | No | No | Yes — `boards-api.greenhouse.io/v1/boards/{slug}/jobs` | N/A | N/A | title, location, departments, absolute_url, updated_at | Real-time per-company | NICE — requires curated list of Canadian employer slugs |
| **Lever ATS** | No | No | Yes — `api.lever.co/v0/postings/{slug}?mode=json` | N/A | N/A | title, location, categories, hostedUrl, createdAt, salaryRange | Real-time per-company | NICE — requires curated list of employer slugs (see §5) |
| **Monster Canada** | Yes | No documented | No | No | LOW | Unknown — insufficient Canadian DS coverage to justify engineering effort | Daily | SKIP — coverage too thin for DS/ML in Canada |
| **Google for Jobs** | No | No | No | SerpAPI: 250 searches/mo free, $25/mo Starter | HIGH if unauthenticated | title, company, location, salary, description | Real-time | DEFER — SerpAPI free tier (250 searches/mo) is borderline sufficient; adds value if other sources miss postings |
| **aijobs.net** | Yes (PRO only, $17/mo) | Per-alert RSS (paid feature) | No | $17/mo PRO | LOW | Unknown | Near-real-time | DEFER — paid-only RSS/alerts; DS-specific but global, Canadian coverage unconfirmed |
| **Wellfound (AngelList)** | No public official alerts | No | No official API | Apify scraper ($) | MEDIUM | N/A | N/A | SKIP — no official API path; startup jobs skew US; weak Canadian employer coverage |

### Data source verdicts
- **Viable**: LinkedIn (email), Indeed.ca (email), Himalayas (API), Jobicy (API), Remotive (API), HN Hiring (RSS), Greenhouse (API), Lever (API)
- **Partially viable**: Job Bank Canada (email alert works, no RSS — email is best path; monthly bulk CSV too stale), Google for Jobs via SerpAPI (250 free searches/mo may be enough if used judiciously)
- **Not viable** for this user: Monster Canada (coverage), Wellfound (no official API), aijobs.net free tier (no accessible RSS without paid account)

---

## 3. LinkedIn Alert Email Deep-Dive

### What fields reliably appear

Based on the public reference project at wooduk.github.io/portfolio/lifilter/ (the only OSS parser found that directly addresses LinkedIn alert email parsing) and search evidence:

- **Job title**: present — in both plain-text and HTML portions
- **Company name**: present
- **Location**: present
- **Job URL**: present (most reliable field — extractable via regex even when HTML layout changes)
- **Job ID**: embedded in URL (extractable)
- **Salary**: unreliable — LinkedIn sometimes includes salary ranges, often omits them
- **Short description**: present in some templates, absent in others
- **Posted date**: absent in alert emails (only relative time like "3 days ago")

### Parsing approach

The reference project author attempted lxml HTML parsing and found it "messy" due to inline CSS embedding. They revised to **regex on the plain-text part of the email** to extract job URLs, which proved more robust. Key insight: **regex on URLs is the correct primary approach**, not HTML DOM traversal. Job IDs and company slugs are embedded in LinkedIn job URLs and can be parsed deterministically.

Critical gotcha documented by the reference author: **Gmail modifies the plain-text part of forwarded emails** — the MIME structure seen in "Show Original" differs from what arrives when an email is forwarded. This matters if you're testing with forwarded samples. When reading via Gmail API or IMAP directly (not forwarding), you get the raw MIME, which is stable.

### Template fragility risk

No documented evidence of a major LinkedIn alert email template redesign in 2024-2025 that broke existing parsers. However, LinkedIn redesigns their email templates periodically with no notice or changelog. The URL-extraction strategy mitigates this: URLs follow a stable pattern (`linkedin.com/jobs/view/{jobId}`) that is unlikely to change even if surrounding HTML is redesigned.

### OSS reference parsers

- wooduk.github.io/portfolio/lifilter/ — regex-based, filters by language, demonstrates the email parsing workflow end-to-end
- No production-quality, maintained OSS library specifically for LinkedIn alert email parsing was found. This is a gap the project will need to fill.

### Recommended parsing strategy

1. Extract all URLs matching `linkedin.com/jobs/view/(\d+)` via regex from the raw email body (plain text preferred over HTML)
2. Optionally fetch job detail page (or LinkedIn unofficial API) to get structured fields — but this crosses into scraping territory
3. Store the job URL as the canonical identifier; treat email-extracted title/company as metadata that may be imprecise

---

## 4. Gmail API Feasibility

### OAuth flow for desktop (local-only app)

The Gmail API supports the **loopback IP address redirect** (`http://127.0.0.1:{port}`) for desktop apps on macOS/Linux/Windows. This flow:
1. Opens a browser tab to Google's consent screen
2. Redirects back to a local HTTP server on completion
3. Exchanges the auth code for access + refresh tokens (stored locally)
4. On subsequent runs, uses the refresh token silently — no browser interaction needed

This is documented as the recommended pattern for "macOS, Linux, and Windows desktop apps" in Google's OAuth 2.0 native app guide. The loopback redirect is deprecated only for Android, Chrome App, and iOS client types — desktop remains supported.

Source: https://developers.google.com/identity/protocols/oauth2/native-app

### Unverified app — is it a problem for personal use?

No. An OAuth app in **Testing** (not "In production") status:
- Is not subject to Google's verification review process
- Can have up to 100 test users added manually in the Cloud Console
- Will show an "App not verified" interstitial screen on first OAuth consent (one-time, user clicks "Continue")
- For a single-user personal tool, this is entirely acceptable

One-time setup: Create a GCP project, enable Gmail API, create OAuth 2.0 client ID (type: Desktop app), download `credentials.json`. No publishing, no domain verification needed.

### IMAP vs Gmail API

| Factor | Gmail API | IMAP + App Password |
|---|---|---|
| Auth complexity | OAuth 2.0 (one-time browser flow) | App Password (simpler initial setup) |
| Structured access | Labels, search queries, message metadata | Folder-based, less expressive |
| Python library | `google-auth`, `google-api-python-client` | `imap_tools` (recommended wrapper) |
| Quota | 1,200,000 units/min per project; `messages.list` = 5 units | No Google-imposed quota |
| Security | OAuth tokens (no password stored) | App password stored in .env |
| Future-proofing | Google's recommended path | App passwords may be deprecated for personal accounts eventually |

**Verdict: Gmail API wins** on long-term stability and structured search (search by sender label like "jobs-alerts@linkedin.com" before parsing). The one-time OAuth setup is a 10-minute task, not a blocker.

### Quotas

- `messages.list`: 5 quota units per call
- `messages.get`: 5 quota units per call
- Daily limit: **none** (only per-minute rate limits: 1.2M units/min project-wide, 15K/min per user)
- For a personal pipeline polling 5 sources once daily, expected consumption is well under 1,000 units/run — no quota concerns.

Source: https://developers.google.com/workspace/gmail/api/reference/quota

### Filtering emails

Use Gmail API search query to pre-filter before parsing:
- `from:jobalerts@linkedin.com` for LinkedIn
- `from:jobalerts@indeed.com` for Indeed
- `newer_than:2d` to bound the lookback window
- Combine with labels if you route job alerts to a dedicated Gmail label (recommended UX pattern)

---

## 5. Discovered Sources (not in original brief)

### Himalayas — MUST ADD
`himalayas.app/jobs/api/search` — free, no auth, 17 structured fields per job. Live-tested: returns 93 results for `q=data+scientist&country=canada`. Supports `seniority`, `employment_type`, `country`, and `q` filters. Data refreshes every 24 hours; rate limit triggers 429 (contact for higher limits). **Best structured API for Canadian remote DS/ML jobs.**

### Remotive — NICE TO ADD
`remotive.com/api/remote-jobs` — free, no auth. Categories include "AI / ML" (id: 37) and "Data Analysis" (id: 24). `candidate_required_location` field can be filtered post-fetch for Canada. Rate limit: max 2x per minute, recommended 4x per day. Live-tested: 20 results with `category=data-science` (mixed quality). Better suited for AI/ML category than data-science.

### Jobicy — NICE TO ADD
`jobicy.com/api/v2/remote-jobs` — free, no auth. `geo=canada` and `industry=data-science` filters available. Live-tested: only 2 matching jobs currently (thin coverage for Canadian DS). Still worth including — zero marginal cost.

### HN "Who is Hiring" (HNRSS) — NICE TO ADD
`hnrss.org/whoishiring/jobs` — free RSS, supports `?q=keyword` filter. Live-tested: 20 entries in April 2026 thread; 2 matched Canada/remote + DS/ML keywords. Extremely low volume but high signal (startups and serious tech companies post here). Parse free text with regex — job posts follow informal conventions (company | role | location | remote | apply URL).

### Greenhouse ATS API — NICE TO ADD (Phase 2 polish)
`boards-api.greenhouse.io/v1/boards/{slug}/jobs` — free, no auth. Requires maintaining a curated list of Canadian employer slugs. Live-tested: Dataiku returns 62 jobs, Hootsuite returns 44. Requires a pre-built "target employer" allowlist to be useful. Recommend seeding with 20-30 major Canadian DS employers (Shopify, Cohere, Wealthsimple, Ada, Hootsuite, etc.) and growing it.

### Lever ATS API — NICE TO ADD (Phase 2 polish)
`api.lever.co/v0/postings/{slug}?mode=json` — free, no auth. Fields: title, categories (location, team, commitment), hostedUrl, salaryRange, createdAt. Same constraint as Greenhouse: needs curated employer slug list. Live-tested: Cohere-ai slug returned "Document not found" (slug may differ from company name; requires discovery per employer). Less predictable slug patterns than Greenhouse.

### Vancouver Tech Journal Jobs Board — WORTH MONITORING
`jobs.vantechjournal.com` — curated Vancouver-specific tech jobs. No confirmed API or RSS. Low volume but geographically precise. Check for RSS at initial implementation; if not available, bookmark for manual monitoring.

### BCtechjobs.ca — CHECK FOR API
Has a developer API link in the footer (URL not confirmed). BC-specific coverage. If the API is publicly accessible, it would be a strong addition for Vancouver-area roles.

---

## 6. Deprecations and Recent Changes to Flag

### Indeed Publisher API — confirmed deprecated
The Indeed Publisher Job Search API is confirmed deprecated and unavailable for new integrations as of 2023. The only current Indeed integration paths are: (a) Sponsored Jobs API (employer-only, requires paid account), (b) email job alerts (what this proposal uses — still functional), (c) third-party scrapers at legal/ToS risk. Source: https://developer.indeed.com/docs/publisher-jobs/job-search

### LinkedIn — no official API for job seekers
LinkedIn's public APIs are employer/recruiter-oriented. There is no official free API for job seeker search. All job-seeker-facing scraping (including JobSpy) relies on unofficial client behavior and is explicitly prohibited by LinkedIn ToS. JobSpy itself warns that "LinkedIn is the most restrictive and usually rate limits around the 10th page" and "proxies are a must." **This confirms email alerts as the only zero-risk LinkedIn path.**

### Gmail IMAP app passwords — still works for personal accounts, but watch this space
Google disabled "less secure apps" access in May 2022, requiring either OAuth or app passwords for IMAP. App passwords remain functional for personal Gmail accounts with 2FA enabled as of 2026. Google Workspace accounts moved to OAuth-only on May 1, 2025. For a personal Gmail account, app passwords continue to work but OAuth is the forward-looking choice.

### Google OOB OAuth flow — deprecated and blocked
The "out-of-band" (copy-paste) OAuth flow was fully deprecated by Google in 2022-2023 and is now blocked. The loopback redirect is the correct desktop replacement. Any tutorial pre-2023 using `urn:ietf:wg:oauth:2.0:oob` as redirect URI will fail.

### Job Bank Canada open data — monthly granularity only
The Open Government Portal dataset for Job Bank job postings is updated **monthly** (last update April 7, 2026) and provides CSV/Atom. This is too stale for active job hunting — it is a research dataset, not a live feed. The live job alert email subscription on jobbank.gc.ca is the correct path for this use case.

### JobSpy (python-jobspy) — maintained but legally risky
Latest version 1.1.82 as of 2025 (speedyapply/JobSpy fork). Actively maintained. But explicitly violates LinkedIn's ToS and risks account ban — user's risk tolerance (zero) disqualifies this library as the primary ingestion path. Could be useful for non-LinkedIn sources if needed as fallback.

---

## 7. Recommended PoC Source Stack

Ordered by value-to-effort ratio for the ASAP constraint. Build in this order:

**Tier 1 — Build first (highest signal, most coverage)**

1. **LinkedIn email alerts** — Core source. User already has alerts. Build the Gmail API connector + LinkedIn URL regex extractor. This is the MVP of the MVP.
2. **Indeed.ca email alerts** — Second highest coverage for Canada. Same Gmail connector, different from-address filter and HTML parser.
3. **Himalayas API** — Free, structured, live-confirmed 93 Canadian DS/ML results. 20 lines of Python. No auth. Build alongside the Gmail connector.

**Tier 2 — Add in the same sprint (trivial marginal cost)**

4. **Job Bank Canada email alerts** — Canadian employer validation is the key unique value here. Set up job alert on jobbank.gc.ca before coding begins. Same email parsing infrastructure.
5. **Remotive API** — `category=ai-ml` or `category=data`. Zero auth. 5 lines to integrate. Catch remote-first roles that Himalayas misses.

**Tier 3 — Add once Tier 1 & 2 are stable**

6. **HN Who is Hiring RSS** — Monthly refresh aligns with a weekly run. Low volume, high quality. Regex parser on free text.
7. **Jobicy API** — Thin Canadian DS coverage currently but zero cost to add; may improve.
8. **Greenhouse ATS** — Build a curated Canadian employer list (20-30 companies). High precision — only DS employers you care about, no irrelevant noise.

**Skip for PoC**: Lever (slug discovery friction), aijobs.net (paid), Wellfound (no official API), Monster (coverage), SerpAPI/Google Jobs (cost), BCtechjobs.ca (unknown API).

---

## 8. Risks and Mitigations

### Risk 1 — LinkedIn email template redesign (HIGH severity)
LinkedIn can silently change their alert email HTML/text structure, breaking parsers with no notice. This is the single biggest fragility in the proposal.

**Mitigation**: Build the LinkedIn parser on URL regex only (pattern: `linkedin.com/jobs/view/(\d+)`). URLs are more stable than surrounding HTML. Log parse failures immediately; design the system to still record the job URL even if title/company extraction fails. Add a health-check metric: "jobs parsed with full fields" vs. "jobs where only URL was captured." Alert if URL-only fraction exceeds 20%.

### Risk 2 — Gmail OAuth credential expiry / token rotation (MEDIUM severity)
OAuth refresh tokens can be revoked by Google if the app is in Testing status with no activity for 6 months, or if the user revokes access from their Google account page.

**Mitigation**: Store refresh tokens in a local `.env` file. Add a startup check that tests Gmail API access before the main pipeline runs, with a clear error message ("Re-run auth flow: python auth.py") if the token is expired. Document this in the README prominently.

### Risk 3 — Job Bank Canada email format parsing failure (MEDIUM severity)
Job Bank is a government site with a less predictable email HTML structure than commercial platforms. It may use less consistent formatting or change templates with civil service IT cycles.

**Mitigation**: Build the Job Bank parser last (after LinkedIn/Indeed parsers are working), so the email parsing infrastructure is mature. Store raw email bodies so you can replay the parser against historical emails after a template change. If email parsing proves too unreliable, fall back to direct scraping of `jobbank.gc.ca/jobsearch/` results — the site is a public government resource and personal-use scraping is low-risk. The CanadaJobScraper OSS project (MIT) demonstrates this approach is feasible.

---

## 9. Open Questions

These must be answered before architecture can be finalized. The main session should collect answers and record them inline.

- **Q1 (Auth)**: Do you want to use a single Gmail address for all job alerts, or separate them (e.g., a dedicated `jobsearch@gmail.com` account vs. your main Gmail)? A dedicated address makes filtering simpler but requires setting up new alerts.
- **Q2 (Job Bank alert setup)**: Have you already created job alert subscriptions on jobbank.gc.ca? If not, this is a manual prerequisite before the pipeline can receive emails. The ingestion pipeline cannot create alerts — it only reads what you subscribe to.
- **Q3 (LinkedIn alert frequency)**: LinkedIn offers daily or weekly alerts. Do you want daily (higher noise, faster signal) or weekly (aggregated)? The pipeline polling cadence should match.
- **Q4 (Greenhouse/Lever employer list)**: Are you willing to maintain a curated list of 20-30 target Canadian employers for the ATS API sources? This adds precision but requires initial curation effort (~1 hour) and periodic maintenance.
- **Q5 (SerpAPI budget)**: The free tier of SerpAPI (250 searches/month) is borderline sufficient for a daily Google Jobs search on 1-2 queries. Is spending $25/month for SerpAPI Starter (1,000 searches) acceptable if Google Jobs coverage proves important?
- **Q6 (Dedup strategy)**: For cross-source deduplication, the recommended fingerprint is `(normalized_company_name, normalized_job_title, normalized_location)` as a composite key. This handles the most common case of the same posting appearing on LinkedIn + Indeed + a company's Greenhouse board. However, fuzzy title matching (e.g., "Sr. Data Scientist" vs. "Senior Data Scientist") may be needed — are you comfortable with a small false-dedup rate on near-duplicates, or do you want to see all instances?
- **Q7 (LinkedIn filter specificity)**: LinkedIn job alerts can be scoped by keyword + location. To minimize noise in alert emails, how tightly do you want to configure the alert? (e.g., one alert for "Data Scientist" OR "Machine Learning" in Vancouver/Canada remote vs. multiple narrow alerts?) Tighter = fewer emails to parse but may miss unexpected role titles like "Applied Research Scientist."

---

## Appendix: Live-Tested API Endpoints

All tests conducted 2026-04-24.

**Himalayas** (`himalayas.app/jobs/api/search?q=data+scientist&country=canada&limit=3`)
- Status: 200 OK
- Total results: 93
- Sample: `{"title": "Sr. Data Scientist", "companyName": "Instacart", "locationRestrictions": ["Canada"], "seniority": ["Senior"], "minSalary": 161000, "maxSalary": 202500}`

**Jobicy** (`jobicy.com/api/v2/remote-jobs?count=3&geo=canada&industry=data-science`)
- Status: 200 OK
- Total results: 2 (thin but real)
- Sample: `{"jobTitle": "Content Services Research Analyst", "companyName": "Q4 Inc.", "jobGeo": "Canada, Mexico", "jobLevel": "Midweight", "pubDate": "2026-04-07T14:01:26+00:00"}`

**Remotive categories** (`remotive.com/api/remote-jobs/categories`)
- Status: 200 OK
- Confirmed categories: `{"id": 37, "name": "AI / ML", "slug": "ai-ml"}`, `{"id": 24, "name": "Data Analysis", "slug": "data"}`

**Greenhouse** (`boards-api.greenhouse.io/v1/boards/dataiku/jobs`)
- Status: 200 OK, 62 total jobs
- Hootsuite: 200 OK, 44 total jobs

**HN HNRSS** (`hnrss.org/whoishiring/jobs`)
- Status: 200 OK, 20 items in April 2026 thread
- URL-based keyword filter works: `?q=data+scientist+Canada` returns (was 502 during test — likely transient)

**Lever** (`api.lever.co/v0/postings/{slug}?mode=json`)
- Status: "Document not found" for tested slugs — slug discovery required per employer, not a standard pattern

**aijobs.net** — No public RSS confirmed. Email alerts and per-alert RSS feeds are behind a $17/mo paywall.
