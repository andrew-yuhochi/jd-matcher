# jd-matcher — Manual Setup Checklist

> **Who this is for**: You, the sole user, doing a one-time setup before M1 can run end-to-end.
> **Time estimate**: 30–45 minutes spread across two sessions (GCP setup + LinkedIn/Indeed alert setup).
> **Source of truth for each step**: DATA-SOURCES.md §"Manual setup checklist" (order preserved here).

---

## Setup Status

Track progress across sessions by checking off each step below.

| Step | Description | Status |
|------|-------------|--------|
| 1 | Dedicated Gmail account confirmed | [ ] |
| 2 | GCP project created + Gmail API enabled | [ ] |
| 3 | OAuth 2.0 client created + credentials.json placed | [ ] |
| 4 | Environment variables configured in `.env` | [ ] |
| 5 | LinkedIn saved searches created (20 alerts: 8 terms, Data Scientist split-by-level) | [x] |
| 6 | Indeed.ca saved searches created (20 alerts: 10 terms, no experience filter) | [x] |
| 7 | Job Bank Canada alerts — DEFERRED TO M4 | — |
| 8 | CV variants placed in local folder — DEFERRED TO M4 | — |
| 9 | `python -m jd_matcher.auth` — first-run OAuth (lands in TASK-M1-004) | [ ] |
| 10 | Sanity-check pipeline run (lands in TASK-M1-008) | [ ] |

**Total saved searches: 40 alerts (LinkedIn 20 + Indeed 20).** Setup complete as of 2026-04-24.

---

## Steps

### 1. Confirm dedicated Gmail account for jd-matcher alerts

**Why**: The Gmail ingester filters inbound messages by sender address (`jobalerts-noreply@linkedin.com`, `alert@indeed.com`). All job alert subscriptions must land in a single dedicated account — mixing with your personal Gmail would require more complex filters and risks false positives.

- ✅ Confirm you have (or create) a Gmail account used exclusively for job-search alerts.
- ✅ Note the address — you will add it as a GCP Test User in step 3.
- ✅ You do not need to configure any Gmail labels for M1, though adding a label like `job-alerts` is a clean UX practice (DATA-SOURCES.md §Gmail — "Optional Gmail label for routing").

> See DATA-SOURCES.md §"Gmail (transport)" for the full sender-filter list and polling cadence details.

---

### 2. Create a GCP project and enable the Gmail API

**Why**: The pipeline reads your job-alert inbox via the Gmail API, not IMAP. Gmail API wins on structured search queries (filter by sender before parsing) and long-term stability (see DATA-SOURCES.md §Gmail and RESEARCH-REPORT.md §4 for the IMAP vs. Gmail API trade-off).

- ✅ Go to [console.cloud.google.com](https://console.cloud.google.com).
- ✅ Click the project dropdown (top-left) → **New Project**. Name it `jd-matcher` (any name works — it is your private project).
- ✅ With the new project selected, go to **APIs & Services** → **Library**.
- ✅ Search for **Gmail API** → click it → click **Enable**.

No billing setup required for the Gmail API at personal-use volume (well under the free quota — see DATA-SOURCES.md §Gmail for quota numbers).

---

### 3. Create an OAuth 2.0 client (Desktop app type) and place credentials.json

**Why**: The Desktop app OAuth type uses a loopback redirect (`http://127.0.0.1:{port}`) — the correct flow for a local Python tool that has no web server and no published redirect URI. This is Google's recommended pattern for macOS/Linux desktop apps and requires no domain verification. An unverified app in Testing status supports up to 100 test users, which covers your use case permanently. See RESEARCH-REPORT.md §4 ("OAuth flow for desktop (local-only app)" and "Unverified app — is it a problem for personal use?") for the full rationale.

- ✅ In GCP Console → **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth Client ID**.
- ✅ Application type: **Desktop app**. Name: `jd-matcher desktop` (any name).
- ✅ Click **Create**. Download the generated `credentials.json`.
- ✅ Place the file at `~/.jd-matcher/credentials.json`. Create the directory if it does not exist:
  ```bash
  mkdir -p ~/.jd-matcher
  mv ~/Downloads/client_secret_*.json ~/.jd-matcher/credentials.json
  ```
- ✅ Back in GCP Console → **APIs & Services** → **OAuth consent screen** → **Test users** → **Add users**. Add your dedicated Gmail address from step 1.
- ✅ Confirm `GMAIL_OAUTH_CLIENT_PATH` in `.env` matches the path (see step 4).

> The first pipeline run will open a browser tab for one-time consent. Subsequent runs reuse the stored refresh token silently (step 9).

---

### 4. Configure environment variables in `.env`

**Why**: The pipeline reads secrets from `.env` at startup. `.env.example` (created by TASK-M1-001) lists every variable with placeholder values.

- ✅ Copy the example file:
  ```bash
  cp .env.example .env
  ```

#### OpenAI API key setup

**Why**: M2 uses `gpt-4o-mini` for structured field extraction and `text-embedding-3-small` for dedup embeddings (DISCOVERY-NOTES §10, TDD §1.3). Both calls go through the same key. Estimated PoC cost: ~$0.65/month at 20 postings/day ($0.60 extraction + $0.04 embeddings), so a $5 cap gives ~7× headroom.

- ✅ Sign in (or create an account) at [platform.openai.com](https://platform.openai.com).
- ✅ Navigate to **API Keys**: [platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys).
- ✅ Click **Create new secret key** → name it `jd-matcher` → leave permissions at the default → click **Create**.
- ✅ **Copy the key immediately.** OpenAI shows it exactly once — if you close the dialog without copying, you must create a new key.
- ✅ Paste it into `.env`:
  ```
  OPENAI_API_KEY=sk-...
  ```
- ✅ Set a monthly budget cap before any production use — go to **Settings → Limits** (or [platform.openai.com/account/limits](https://platform.openai.com/account/limits)) and set a **hard cap of $5–10**. Optionally set a soft email warning at $2.
- ✅ Verify the key works once `.env` is populated:
  ```bash
  .venv/bin/python -m jd_matcher.llm.smoke
  ```
  Expected: a one-line success message confirming the model responded (e.g. `[jd-matcher] OpenAI smoke test passed — model: gpt-4o-mini`).

> Never commit `.env` to git — it is already listed in `.gitignore`. Only `.env.example` (which contains a blank placeholder for `OPENAI_API_KEY`) is committed.

- ✅ Set the credentials path:
  ```
  GMAIL_OAUTH_CLIENT_PATH=~/.jd-matcher/credentials.json
  ```

- ✅ `GH_TOKEN` was already populated during TASK-M1-001 repo bootstrap — leave as-is.

- ✅ Leave `DB_PATH` at its default (`~/.jd-matcher/jd-matcher.db`) unless you want the database somewhere else.

---

### 5. Set up LinkedIn saved searches

**Why**: LinkedIn's alert emails are the primary source for Vancouver / Remote-Canada DS roles. The pipeline never logs into LinkedIn — the platform pushes the list to your Gmail via daily alert emails, which the ingester then reads. Missing a role is worse than getting duplicate emails (the dedup layer collapses overlap for free), so coverage should be generous. See DATA-SOURCES.md §"LinkedIn (via Gmail alerts)".

**LinkedIn has a 20-alert cap.** Allocate those slots by term-relevance rather than distributing them equally.

**Location design**: Each alert is scoped to one of two locations — **Greater Vancouver Metropolitan Area** (broader catchment that includes Burnaby, Surrey, and Richmond) or **Canada (On-site/Remote = Remote)**. Splitting locations forces the algorithm to surface the strongest match for each location independently; the dedup layer collapses any overlap.

**Alert allocation strategy (actual setup, 2026-04-24):**

`Data Scientist` is the closest-fit term to the user's profile. It gets dedicated split-by-experience-level alerts per location to maximize email-digest exposure across all seniority bands and capture misclassified-as-Entry postings. The other 7 terms each get one combined-level (Entry + Senior + Manager) alert per location.

| Term | Experience filter | Alerts |
|------|------------------|--------|
| `Data Scientist` | Entry-level (per location) | 2 |
| `Data Scientist` | Senior (per location) | 2 |
| `Data Scientist` | Manager (per location) | 2 |
| `Machine Learning Engineer` | Entry + Senior + Manager (per location) | 2 |
| `Applied Scientist` | Entry + Senior + Manager (per location) | 2 |
| `Data Science` | Entry + Senior + Manager (per location) | 2 |
| `Research Scientist` | Entry + Senior + Manager (per location) | 2 |
| `Senior Data Analyst` | Entry + Senior + Manager (per location) | 2 |
| `AI Engineer` | Entry + Senior + Manager (per location) | 2 |
| `Quant Research` | Entry + Senior + Manager (per location) | 2 |
| **Total** | | **20** |

**Terms dropped due to the 20-alert cap:**

- `Senior Data Scientist` — redundant with the `Data Scientist` split-by-level setup; the Senior filter already captures this tier.
- `Applied AI Research` — overlaps strongly with the `Applied Scientist` + `Research Scientist` union; cap pressure forced trimming.

Both terms are retained in the Indeed setup where no experience filter is applied and the 20-cap is filled by unique keywords only.

**How to create one LinkedIn saved search:**

Example: `Data Scientist` — Entry-level, Greater Vancouver Metropolitan Area:

1. Go to [linkedin.com/jobs](https://linkedin.com/jobs).
2. Enter `Data Scientist` in the search bar → press Enter.
3. In the **Location** filter, type and select `Greater Vancouver Metropolitan Area`.
4. Open the **Experience level** filter → select **Entry level** only.
5. Leave the On-site/Remote filter at its default (this is the city-specific search).
6. Click the bell icon on the results page → set frequency to **Daily** → confirm.

Then repeat for the Remote-Canada search (same term + experience level, different location):

1. Same keyword `Data Scientist`, same Experience level filter (`Entry level`).
2. Clear the location field; type and select `Canada`.
3. Open **On-site/Remote** filter → select **Remote** only.
4. Bell icon → Daily → confirm.

For the 7 other terms (no experience-level split): set **Experience level** to Entry level + Senior + Manager combined, and repeat the two-location pattern per term.

> If the platform UI has changed and the filter combos above don't map cleanly, apply the concept: one search scoped to Greater Vancouver, one scoped to Remote-Canada; Data Scientist split by level, all others combined-level.

Estimated time: ~30 seconds per search × 20 searches = **~10 minutes**.

Sender filter the ingester uses: `jobalerts-noreply@linkedin.com` (DATA-SOURCES.md §"LinkedIn (via Gmail alerts)").

> Full alert specification is machine-readable in `config/saved-searches.yaml` (linkedin.alerts).

---

### 6. Set up Indeed.ca saved searches

**Why**: Indeed is the second-highest-coverage source for Canada. The Publisher API was deprecated in 2023; daily email alerts are the only zero-risk path. See DATA-SOURCES.md §"Indeed.ca (via Gmail alerts)".

**No experience filter applied.** Indeed's experience-level filter is unreliable — it frequently miscategorizes postings or omits results that should match. All 20 Indeed alerts are set up without any experience filter. Seniority triage is handled downstream by the keyword prefix (e.g. `Senior Data Scientist`) combined with the pipeline's seniority hard-filter (implemented in M2).

**Location design**: One search scoped to `Vancouver, BC` (Where field), one scoped to `Canada` with the Remote toggle on. Same split-location rationale as LinkedIn — forces the algorithm to surface the strongest match for each location independently; dedup collapses overlap.

**Result: 10 terms × 2 locations = 20 Indeed saved searches.**

**Finalized keyword list (user-approved 2026-04-24):**

| # | Keyword | Notes |
|---|---------|-------|
| 1 | `Data Scientist` | |
| 2 | `Senior Data Scientist` | Title prefix covers seniority (no filter needed) |
| 3 | `Machine Learning Engineer` | |
| 4 | `Applied Scientist` | |
| 5 | `Data Science` | |
| 6 | `Research Scientist` | |
| 7 | `Senior Data Analyst` | Title prefix covers seniority |
| 8 | `AI Engineer` | |
| 9 | `Applied AI Research` | Retained on Indeed (dropped from LinkedIn due to cap) |
| 10 | `Quant Research` | |

**How to create one Indeed saved search (repeat this pattern 20 times):**

Example: `Data Scientist` — Vancouver location search:

1. Go to [indeed.ca](https://indeed.ca).
2. In the **What** field, enter `Data Scientist`.
3. In the **Where** field, enter `Vancouver, BC`.
4. Run the search. Do NOT apply any experience-level filter.
5. On the results page, click **Get new jobs by email** (or the bell icon if shown).
6. Select frequency **Daily** → enter your dedicated job-search Gmail address → confirm.

Then repeat for the Remote-Canada search:

1. Same keyword `Data Scientist`.
2. **Where** field: enter `Canada`.
3. After the search runs, locate the **Remote** toggle or filter and enable it. Do NOT apply any experience-level filter.
4. Get new jobs by email → Daily → confirm.

> If the platform UI has changed and the filter combos above don't map cleanly, apply the concept: one search scoped to Vancouver city, one scoped to Remote-Canada only. No experience filter on any Indeed alert.

Estimated time: ~30 seconds per search × 20 searches = **~10 minutes**.

Indeed alert emails include title, company, location, URL, and partial salary when available. Indeed rewrites links via tracking redirectors — the pipeline resolves these to canonical URLs automatically (DATA-SOURCES.md §"Indeed.ca" — "Known limitations"). No action needed on your end.

Sender filter the ingester uses: `alert@indeed.com` (DATA-SOURCES.md §"Indeed.ca (via Gmail alerts)").

> Final list is machine-readable in `config/saved-searches.yaml`.

---

### 7. Set up Job Bank Canada email alerts — DEFERRED TO M4

**Not blocking M1.** Job Bank Canada (`jobbank.gc.ca`) is the highest-differentiation source for OWP holders — every employer listed is validated as Canadian-eligible-to-hire, which directly addresses your work-permit filter. No competitor surfaces this signal. See DATA-SOURCES.md §"Job Bank Canada (via Gmail alerts) — M4" and MARKET-ANALYSIS.md §"PoC/MVP Implications".

**Steps for when M4 arrives:**
1. Go to [jobbank.gc.ca](https://www.jobbank.gc.ca/jobsearch/).
2. Search for `Data Scientist` + Location: `Vancouver, British Columbia` + check **Remote**.
3. Click **Get email alerts** → enter your dedicated Gmail address → confirm.
4. Repeat for `Machine Learning` and any other keywords decided at M4.
5. Note the sender address for the ingester: `noreply@jobbank.gc.ca` family (verified during M4 implementation — DATA-SOURCES.md §"Job Bank Canada").

The Job Bank email parser (C13) lands in TASK-M4-xxx. Document the sender address and keyword choices in SETUP.md at that point.

---

### 8. Place 5 CV variants in local folder — DEFERRED TO M4

**Not blocking M1.** The CV recommender (C24) lands in M4 and ranks your 5 CV variants against each posting by cosine similarity. See TDD.md §C24.

**Placeholder for when M4 arrives:**
- ✅ Place your 5 CV PDFs at `~/.jd-matcher/cvs/`. Example:
  ```
  ~/.jd-matcher/cvs/cv-ml-research.pdf
  ~/.jd-matcher/cvs/cv-applied-ds.pdf
  ~/.jd-matcher/cvs/cv-nlp.pdf
  ~/.jd-matcher/cvs/cv-causal.pdf
  ~/.jd-matcher/cvs/cv-finance-ds.pdf
  ```
- ✅ Give each a short nickname and one-line purpose description — these are wired into M4 config. The M4 setup task will ask you for them explicitly.

No action needed now.

---

### 9. Run first-run Gmail OAuth authorization

**Lands in TASK-M1-004** (Gmail ingester implementation). Once that task is complete, run:

```bash
python -m jd_matcher.auth
```

What this does:
1. Reads `credentials.json` from `GMAIL_OAUTH_CLIENT_PATH`.
2. Opens your browser to Google's consent screen.
3. You click **Continue** past the "App not verified" interstitial (expected — see step 3 rationale).
4. Authorize access to Gmail (read-only scope).
5. Stores the refresh token at `~/.jd-matcher/tokens.json`.

On all subsequent pipeline runs, the token is reused silently — no browser interaction needed. If the token expires (90+ days of inactivity or manual revocation), re-run this command. The pipeline surfaces a persistent banner if the token is invalid (DATA-SOURCES.md §Gmail "Failure mode (Risk 2 / R2)").

---

### 10. Sanity-check pipeline run

**Lands in TASK-M1-008** (pipeline orchestrator implementation). Once M1 implementation tasks are complete:

```bash
python -m jd_matcher.pipeline
```

What this does:
1. Reads Gmail for LinkedIn + Indeed alert emails from the past 2 days.
2. Parses posting URLs from each email.
3. Deduplicates against already-seen URLs.
4. Hydrates each new URL to fetch the full JD (1 request per 30 seconds).
5. Stores all postings in `~/.jd-matcher/jd-matcher.db`.
6. Prints a run summary: sources fetched, new URLs found, URLs deduplicated, hydration success/failure counts, overall health status.

If any source fails, the pipeline prints the failure reason and continues with the remaining sources — per-source isolation means one failure never blocks another (TDD §C11). Full pipeline health details are visible in the browser UI source-health sub-bar once TASK-M1-009 is complete.

Expected output on a healthy first run (after some alert emails have accumulated):

```
[jd-matcher] Pipeline run started — run_id=...
  gmail_linkedin   healthy   N emails fetched, M URLs parsed
  gmail_indeed     healthy   N emails fetched, M URLs parsed
  hydrator_linkedin healthy  M URLs hydrated (0 failed)
  hydrator_indeed  healthy  M URLs hydrated (0 failed)
[jd-matcher] Run complete — X new postings stored. Open http://localhost:8765 to triage.
```

---

## Total setup time estimate

| Component | Time |
|-----------|------|
| GCP project + Gmail API (step 2) | ~5 min |
| OAuth client + credentials.json (step 3) | ~5 min |
| `.env` configuration (step 4) | ~2 min |
| LinkedIn saved searches — 20 searches (step 5) | ~10 min |
| Indeed saved searches — 20 searches (step 6) | ~10 min |
| Miscellaneous (browser, confirmations, tab switching) | ~3 min |
| **Total** | **~30–35 minutes** |

Steps 1–4 and 5–6 can be spread across two sessions. Steps 5 and 6 are the longest but fully mechanical once you have the keyword list in front of you.

---

## Cross-references

| Step | DATA-SOURCES.md section | TASK-ID (code lands here) |
|------|------------------------|--------------------------|
| 1 | §Gmail (transport) | N/A — user action only |
| 2 | §Gmail (transport) — OAuth setup | N/A — user action only |
| 3 | §Gmail (transport) — OAuth setup | TASK-M1-004 (auth module) |
| 4 | §Gmail (transport) | TASK-M1-001 (`.env.example` created) |
| 5 | §LinkedIn (via Gmail alerts) | TASK-M1-004 (Gmail ingester), TASK-M1-005 (LinkedIn email parser) |
| 6 | §Indeed.ca (via Gmail alerts) | TASK-M1-004 (Gmail ingester), TASK-M1-005 (Indeed email parser) |
| 7 | §Job Bank Canada (via Gmail alerts) — M4 | TASK-M4-xxx (to be created at M4 /milestone-plan) |
| 8 | N/A (CV recommender) | TASK-M4-xxx (C24 — CV Recommender) |
| 9 | §Gmail (transport) — OAuth setup | TASK-M1-004 |
| 10 | §"Manual setup checklist" step 10 | TASK-M1-008 |
