# UX Specification — jd-matcher — Discovery

> **Author**: ux-designer
> **Date**: 2026-04-24
> **Phase**: Discovery
> **Input**: `projects/jd-matcher/docs/discovery/DISCOVERY-NOTES.md`
> **Feeds into**: PRD.md §8 User Workflow, TDD.md §1.1 Data Flow

---

## Executive Summary

jd-matcher has one user and one goal: clear 5–20 new job cards per day in under a minute. Every UX decision is evaluated against that goal. The approach is keyboard-first, optically hierarchical card-based layout on a single three-tab web page. There is no onboarding, no instructional text, no decorative chrome. The aesthetic target is Linear / Attio — dense, precise, serious.

---

## User Workflow

### Current state (without jd-matcher)

1. Open LinkedIn and run 7 saved searches sequentially — read titles, open tabs for plausible postings.
2. Repeat for Indeed.ca, then Job Bank Canada.
3. Read full JDs on each tab to determine role fit, noting dashboard-builder vs. DS distinction.
4. Pick one of 5 CVs based on reading the JD requirements.
5. Copy the apply URL into a personal tracker (spreadsheet or mental note).
6. Return next day and cannot remember which postings were seen before — re-skim all or skip manually.

**Total time per day**: 20–45 minutes. Primary friction: manual fit-triage, duplicate recognition, CV selection.

### Desired state (with jd-matcher)

1. Open `localhost:PORT` in browser.
2. See ranked stack of new suitable cards — skim title, company, primary tag, salary in 2 seconds per card.
3. Press `e` to expand any card that looks promising — read full JD, see recommended CV.
4. Press `a` (mark applied) or `d` (dismiss) — card exits the view.
5. All cards cleared — done for the day. < 1 minute for 5–20 cards.

### Friction points & UX targets

| Friction point | Job to be done | UX target |
|---|---|---|
| Can't tell fit from title alone | Infer interest from primary tag + salary before reading JD | Primary tag as largest visual anchor after title |
| Reading full JD mid-triage breaks flow | Expand inline without navigating away | Smooth in-place expand, keyboard-triggered |
| CV selection requires re-reading the JD | Recommend the right CV instantly | CV chip visible in collapsed card, rationale in expanded state |
| Losing track of applied postings | Passive tracking of what user acted on | Applied tab, auto-remove after 3 months |
| Forgot which roles were seen before | System-managed seen/dismissed state | Dismissed permanently hidden from main |

---

## 1. Information Architecture

### Decision: Three-tab top navigation

**Top-level structure**:

```
[ Main (12) ]  [ Applied (5) ]  [ Dismissed ]
```

- **Main** is the default landing tab. Badge count shows number of active cards.
- **Applied** is opened periodically to update status on live applications.
- **Dismissed** is a tab, not a toggle. It is almost never opened — its sole purpose is debugging (e.g., "did I accidentally dismiss a good post?"). No badge count.
- Dismissed tab renders a search box first, then a flat list — it is explicitly not a daily-use surface.

**Rationale**: tabs are the least surprising nav pattern for a single-page app with three view states. A sidebar adds visual mass that a 5-card-per-day tool doesn't earn. Filter toggles would require a persistent filter bar that competes with card space. Three tabs, clear counts, no more UI chrome than that.

**Tab order**: Main → Applied → Dismissed. Tab order matches frequency of use.

### Page shell (constant across all tabs)

```
┌─────────────────────────────────────────────────────────┐
│  jd-matcher          [ Main (12) ] [ Applied (5) ] [ Dismissed ]   [⚙]  │
│─────────────────────────────────────────────────────────│
│  [search /]                               Last sync: 2 min ago   │
│─────────────────────────────────────────────────────────│
│                                                         │
│   [card stack]                                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- Top bar: wordmark (no logo), tabs, settings gear icon.
- Sub-bar: search input (activated by `/`), last-sync timestamp (shows pipeline health at a glance).
- Everything below sub-bar is the card stack.

---

## 2. Card Design — Main View

### Card states

**Collapsed (default)**

This is the triage state. User decides "worth expanding?" in ~2 seconds.

```
┌──────────────────────────────────────────────────────────────┐
│  [LLM / GenAI]  Senior Data Scientist — Shopify              │
│  Vancouver · Senior · $140k–$180k CAD             [Applied] [Dismiss] │
│  Industry: E-Commerce · 2 sources · Today                    │
└──────────────────────────────────────────────────────────────┘
```

Visual hierarchy in collapsed state:

| Layer | Content | Visual treatment |
|---|---|---|
| Primary anchor | Primary technical focus tag | Coloured chip — largest, leftmost on line 1 |
| Title | Canonical job title | Bold, 16px, beside the chip |
| Company | Company name | Bold, same line as title, separated by em-dash |
| Secondary | Location · Seniority · Salary | Muted, 13px, line 2 |
| Tertiary | Industry · Source count · Posting recency | Subtle, 12px, line 3 |
| Actions | [Mark Applied] [Dismiss] | Right-aligned on line 2, appear on hover or keyboard focus |

Line 1 is the decisive read. The user's eye lands on the primary tag first (colour draws it) then sweeps right to title + company. If the tag says `LLM / GenAI` and the title says "Senior Data Scientist — Shopify", the user knows in ~1.5 seconds whether to expand.

**Hover state**

On mouse hover: action buttons `[Mark Applied]` `[Dismiss]` become visible (always present in DOM, opacity transitions from 0 to 1). Keyboard focus achieves the same without hover.

**Expanded state**

Triggered by `e` key or clicking the card body. Card expands in-place — no navigation, no modal overlay.

```
┌──────────────────────────────────────────────────────────────┐
│  [LLM / GenAI]  Senior Data Scientist — Shopify    [Collapse ↑]  │
│  Vancouver · Senior · $140k–$180k CAD                        │
│  Industry: E-Commerce                                        │
│  Tags: [LLM / GenAI] [Recommender Systems] [MLOps / ML Infra]│
│  Sources: LinkedIn · Himalayas                               │
│  ─────────────────────────────────────────────────          │
│  CV: CV-LLM.pdf  ← highest cosine match (RAG + agents focus) │
│  [Open CV-2.pdf ▾]  ← override dropdown, all 5 listed       │
│  ─────────────────────────────────────────────────          │
│  [Open LinkedIn →]  [Open Himalayas →]                       │
│  ─────────────────────────────────────────────────          │
│  About the role                                              │
│  [Full JD text, scrollable, max-height: 400px]               │
│  ─────────────────────────────────────────────────          │
│                       [Mark Applied]  [Dismiss]  [Collapse ↑] │
└──────────────────────────────────────────────────────────────┘
```

Expanded card sections (in order):

1. **Header** — same as collapsed, with `[Collapse ↑]` button top-right.
2. **All tags** — secondary tags displayed as smaller chips below the primary.
3. **Sources** — text list of source names, each linking to the apply URL (duplicate of the explicit apply buttons).
4. **CV recommendation** — `CV-LLM.pdf` as the primary recommendation with a 1-line rationale ("highest cosine match — RAG + agents focus"). Override dropdown shows all 5 CVs ranked by score. User clicks to copy filename (`c` key also copies the recommended filename).
5. **Apply buttons** — one button per source URL, labeled with source name.
6. **Full JD** — full job description text, scrollable within a fixed-height container, not a separate page.
7. **Action row** — `[Mark Applied]` `[Dismiss]` `[Collapse ↑]` — repeated at the bottom so the user doesn't have to scroll back up after reading the JD.

---

## 3. Card Ordering & Density

### Rank communication

Cards are ordered by the soft-rank composite score (salary + industry bonus + recency decay). The UI communicates rank **by position only** — no explicit score badge, no rank number. Rationale: scores are soft estimates based on configurable weights; displaying them invites the user to second-guess the weighting rather than trusting their own eye contact with the card content. Order is self-evident; a number on a card creates cognitive load without adding decision value.

The one exception: if a card's salary is missing (`salary: unknown`), it renders salary field as "Salary not listed" in muted italic — it does not disappear. Users should know the system tried and failed to extract it, not assume it was not specified.

### Density target

**4–5 collapsed cards visible per viewport** (1440px wide × 900px tall). This gives enough context to see the day's queue without scrolling to count, while keeping each card tall enough to read comfortably.

Card collapsed height: approximately 70px. With 8px gap between cards. At 900px viewport minus ~80px shell: ~5 cards.

Cards do not paginate. The main view is a single scrollable stack. With 5–20 cards per day, pagination would add friction rather than remove it.

---

## 4. Keyboard-First Interaction

The keyboard scheme is the most critical UX decision in this spec. The goal: user's hands never leave the keyboard during daily triage.

### Keyboard map

| Key | Action | Notes |
|---|---|---|
| `j` / `↓` | Move focus to next card | Focused card gets a visible outline (2px solid accent) |
| `k` / `↑` | Move focus to previous card | |
| `e` | Toggle expand/collapse focused card | Second `e` collapses |
| `d` | Dismiss focused card | Card slides left 100% and collapses over 180ms, then removed from DOM |
| `a` | Mark applied (focused card) | Card fades out over 150ms and moves to Applied tab |
| `o` | Open first apply URL in new tab | If multiple sources, opens first in list; `shift+o` opens all |
| `c` | Copy recommended CV filename to clipboard | Silent clipboard copy + brief "Copied" toast (1.5s) |
| `/` | Focus search input | Esc returns focus to card list |
| `1` | Switch to Main tab | |
| `2` | Switch to Applied tab | |
| `3` | Switch to Dismissed tab | |
| `?` | Show keyboard shortcut cheatsheet | Modal overlay, Esc to close |
| `Esc` | Collapse expanded card / close cheatsheet / blur search | Priority: cheatsheet > expanded card > search |

### Discoverability

- On first load and every time the card stack is empty, a subtle one-line hint appears below the stack: "Press `?` for keyboard shortcuts". This is the only instructional text in the UI.
- The `?` shortcut opens a modal listing all shortcuts in two columns. No prose — just key → action pairs, same table as above.
- The cheatsheet is the complete in-product documentation. No help page, no tooltip tour.

### Dismiss animation spec

On `d`: the focused card translates `transform: translateX(-100%)` over 180ms (ease-in), then the vertical space collapses over 100ms (height → 0, margin → 0). Total: 280ms. The next card receives focus automatically. This cadence communicates permanence without feeling violent — slower than a swipe, faster than reading.

On `a` (mark applied): card fades `opacity: 0` over 150ms, then collapses height. Lighter animation than dismiss — signals a positive action vs. rejection.

---

## 5. CV Recommendation Affordance

### Decision: top-1 recommendation with rationale + override dropdown

**Collapsed card**: CV name chip only — `CV-LLM.pdf`. No score, no rationale. It fits on one line and is enough to send the user's hand toward the right folder.

**Expanded card**:
- Primary: `CV-LLM.pdf` with a 1-line rationale string generated from extracted fields — e.g., "RAG + agents focus matches top skills" — under 80 characters, no LLM call needed (template-based from top tags and role summary).
- Override: `[▾ Use a different CV]` dropdown listing all 5 CVs with cosine similarity scores shown as simple bars (not percentages — bars are scannable; decimals require math). Clicking any CV in the list sets it as the new recommendation and updates the chip. Override is stored in the DB for that posting.

**Settings page (PoC scope)**: CV management is in the settings page — user enters the 5 CV filenames (not uploads — local filesystem paths). The system stores the filename + embedding. No file upload, no PDF rendering.

**Rationale for top-1 only in collapsed state**: showing top-2 in collapsed state adds a second line of content that competes with the primary CV decision. The override exists in expanded state for users who want to reassess — they expand when uncertain.

---

## 6. Visual Treatment — Tags, Salary, Sources

### Tag chips

| Field | Visual |
|---|---|
| Primary focus tag | Filled chip — 12px semibold text, accent-coloured background (one colour per tag family — see palette below) |
| Secondary tags | Outlined chip — 11px text, muted border, white/dark background |
| Industry | Plain text, muted — not a chip. Too decorative for a secondary signal. |
| Seniority | Plain text, muted — same line as location and salary |
| Salary | `$140k–$180k CAD` — monospace, same muted line. Missing salary: italic `Salary not listed`. |
| Sources | Text list in expanded state. In collapsed state: `2 sources` count — not logos. Logos are decorative and require maintenance as source branding changes. |

### Tag colour palette (per focus family)

Colours must be colour-blind safe — avoid red/green pairs for distinct categories. Use blue/amber/violet/teal/slate spectrum.

| Tag | Chip colour |
|---|---|
| LLM / GenAI | Violet — `#7C3AED` bg, white text |
| Traditional ML | Blue — `#2563EB` bg, white text |
| Causal Inference / Experimentation | Teal — `#0D9488` bg, white text |
| NLP | Sky — `#0284C7` bg, white text |
| Computer Vision | Indigo — `#4338CA` bg, white text |
| Recommender Systems | Amber — `#D97706` bg, white text |
| Time Series / Forecasting | Cyan — `#0891B2` bg, white text |
| MLOps / ML Infra | Slate — `#475569` bg, white text |
| Applied Research | Rose — `#E11D48` bg, white text |
| Business Analytics / BI | Stone — `#78716C` bg, white text — visually dimmed to signal "user typically avoids" |

---

## 7. Applied-State Card

The Applied view has different needs from the Main view — the user is reviewing, not triaging.

### Card layout (Applied tab)

```
┌──────────────────────────────────────────────────────────────┐
│  [LLM / GenAI]  Senior Data Scientist — Shopify              │
│  Vancouver · Senior · $140k–$180k CAD                        │
│  Status: [Applied ▾]   Applied 14 days ago   Removes in 77 days │
│  ─────────────────────────────────────────────────          │
│  Notes: [_______________________________] (click to edit)    │
└──────────────────────────────────────────────────────────────┘
```

### Status options (dropdown)

`Applied` → `Screen` → `Interview` → `Offer` → `Rejected` → `Ghosted`

- Status is always visible, not hidden behind expand.
- Changing status resets the 3-month auto-remove timer only if new status is not terminal (`Rejected` / `Ghosted` — these keep the original timer, because the user probably wants them to expire sooner).
- `Ghosted` is a valid user signal: acknowledges the company stopped responding.
- `Offer` is in the list — the auto-remove timer is paused when status is `Offer` (user may be negotiating).

### Counters

- `Applied 14 days ago` — count from `status_updated_at` of the original `Applied` transition.
- `Removes in 77 days` — countdown from first `Applied` date + 90 days. Always visible so the user can decide to update status before it disappears.

### Notes field

- Single-line text field on the card, click-to-edit inline (no modal). Placeholder: "Interview notes, contact, follow-up…"
- Auto-saves on blur.
- For PoC: plain text only, no formatting. 500-character limit.

### Applied tab ordering

Sorted by `days_since_applied` descending — oldest applications first, so the most stale ones are at the top and prompt action.

---

## 8. Empty States, Loading, Errors

### Main tab — no new postings today

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│              No new postings today.                          │
│              Next sync in 47 minutes.                        │
│                                                              │
│              [Run sync now]                                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

- "No new postings today" — not "No results found" (which implies a query failure). Explicit about the reason.
- Shows next scheduled sync time from config.
- `[Run sync now]` button triggers the pipeline manually. This is the only UI-triggered pipeline action.
- Does NOT show motivational copy or illustrations.

### First-run (zero data ever)

```
┌──────────────────────────────────────────────────────────────┐
│  jd-matcher is running.                                      │
│                                                              │
│  No postings yet. The pipeline runs hourly.                  │
│  First results should appear within the next 60 minutes.     │
│                                                              │
│  [Run sync now]                                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Gmail OAuth failed

```
┌──────────────────────────────────────────────────────────────┐
│  [!] Gmail connection lost. LinkedIn and Indeed alerts       │
│  will not be ingested until reconnected.                     │
│                                                              │
│  [Reconnect Gmail]                                           │
└──────────────────────────────────────────────────────────────┘
```

- Persistent banner at the top of the page — not a toast. Toasts expire; this failure is persistent.
- Does not block the rest of the UI — API sources (Himalayas, Remotive, Jobicy, HN) continue working.
- `[Reconnect Gmail]` opens the OAuth loopback flow.

### LLM pipeline not finished (partial data)

```
┌──────────────────────────────────────────────────────────────┐
│  [i] Pipeline still running — some postings may appear       │
│  without tags or fit scores yet.                             │
└──────────────────────────────────────────────────────────────┘
```

- Informational banner, not an error. Dismissible.
- Cards that are pending LLM processing still appear in the list but show `[Processing…]` in the tag position and have no salary or fit fields. They appear below fully-processed cards.

### Per-source fetch failure

No banner per source failure — too noisy for a daily-use tool. Instead: the `last sync` timestamp in the sub-bar turns amber if any source failed on the last run. Hovering the timestamp shows a tooltip listing which sources failed. For PoC, this is sufficient — the user is technical enough to check logs if needed.

### Applied tab — no applications yet

```
No applications tracked yet.
When you mark a posting as Applied, it appears here.
```

One-line empty state. No illustration.

### Search — no results

```
No postings match "<query>".
```

No suggestion system, no fuzzy fallback. For PoC, exact substring match on title + company is sufficient.

---

## 9. Settings Surface

### PoC scope (minimal — one page at `/settings`)

| Setting | Type | Notes |
|---|---|---|
| Gmail connection status | Status indicator + `[Reconnect]` button | Shows connected email address |
| CV variant filenames | 5 editable text inputs (local filesystem paths) | Labels: CV-1 through CV-5, user can rename |
| Last pipeline run | Read-only timestamp | Debug info |
| Pipeline schedule | Read-only (from config file) | Not editable in UI for PoC |

CV management: user enters the path to each CV file on their filesystem. jd-matcher uses the filename for display and the content (parsed via PyMuPDF or pdfplumber) for embedding at startup. No upload UI — the user manages files on their own machine.

**Not in PoC settings**: soft-rank weights, fit-score threshold, dedup thresholds, tag taxonomy. These remain config-file-driven for PoC. They are flagged as MVP settings candidates.

### MVP settings additions (deferred)

- Soft-rank weight sliders (salary vs. industry vs. recency)
- Fit-score threshold slider with live preview count
- Tag taxonomy editor (rename, merge, add)

---

## 10. Accessibility Notes

This is a single-user personal tool. The accessibility bar is "not unusable", not WCAG AA. The following should be implemented anyway:

- **Keyboard focus ring**: a clearly visible 2px outline on the focused card. Default browser focus rings are insufficient — the card outline must be high-contrast (accent colour) and obvious.
- **Contrast**: body text minimum 4.5:1 against background. Tag chips minimum 3:1 (they are decorative, but still must be legible).
- **Font size**: default 15px body, 16px card title. Never below 12px for any visible element.
- **Chip colour palette**: designed above to avoid red/green reliance.
- **Dismiss animation**: the 180ms translateX uses `prefers-reduced-motion` — if the user has reduced motion enabled, the card disappears immediately (no animation).

---

## What NOT to Build

1. **Fit score badge on collapsed cards** — displaying `fit: 78` next to each card invites the user to optimize around the score rather than their own judgment. The score is used for ordering and filtering; it is not user-facing data.
2. **Notification / push alerts** — the tool is explicitly pull-based. The user opens it when they sit down to job-hunt. Push notifications add complexity and break the "personal desktop tool" model.
3. **Bulk select + bulk dismiss** — the daily volume (5–20 cards) is low enough that per-card keyboard actions are faster than selecting multiple and confirming a bulk action. Adding bulk UI adds chrome without reducing time.
4. **Inline CV editing or rewriting** — the system recommends one of 5 existing CVs. It does not write or modify CVs. No editor, no paste area, no LLM-rewrite button.

---

## Interaction Specification — Per Touchpoint

### Touchpoint 1 — Page load

| | |
|---|---|
| **Trigger** | User navigates to `localhost:PORT` in browser |
| **Input** | None |
| **System response** | Main tab loads with current card stack (pre-sorted). Last-sync timestamp shown. If pipeline is running: informational banner. If Gmail disconnected: error banner. |
| **Error state** | If FastAPI is not running: browser shows connection refused — no in-app UX possible |
| **Exit state** | User sees card stack, ready to triage |

### Touchpoint 2 — Card dismiss (keyboard)

| | |
|---|---|
| **Trigger** | `d` keypress on focused card |
| **Input** | Focused card ID |
| **System response** | POST /cards/{id}/dismiss — card animates out (translateX -100%, 180ms, then height collapse 100ms), focus moves to next card, dismissed count increments |
| **Error state** | API call fails: card snaps back, brief "Dismiss failed" toast (3s) |
| **Exit state** | Card gone from Main. Posting added to dismissed blacklist. |

### Touchpoint 3 — Mark applied (keyboard)

| | |
|---|---|
| **Trigger** | `a` keypress on focused card |
| **Input** | Focused card ID |
| **System response** | POST /cards/{id}/apply — card fades out (150ms), moves to Applied tab with status `Applied`, focus moves to next card |
| **Error state** | API call fails: card snaps back, brief toast |
| **Exit state** | Card gone from Main. Card appears in Applied tab with status `Applied` and timestamp. |

### Touchpoint 4 — Expand card

| | |
|---|---|
| **Trigger** | `e` keypress or click on card body |
| **Input** | Focused card ID |
| **System response** | Card expands in-place — full JD, tags, CV recommendation, apply URLs visible. Expand is CSS height transition (200ms ease-out). |
| **Error state** | JD content missing: show "Full description not available" placeholder in JD section |
| **Exit state** | Card is expanded. Second `e` collapses. |

### Touchpoint 5 — Status update (Applied tab)

| | |
|---|---|
| **Trigger** | Click on status dropdown in Applied card |
| **Input** | New status value |
| **System response** | PATCH /applications/{id}/status — status chip updates in place. If terminal status (Rejected/Ghosted), no timer reset. |
| **Error state** | API call fails: status reverts, brief toast |
| **Exit state** | Status updated. Days counters recalculated where applicable. |

### Touchpoint 6 — Manual sync

| | |
|---|---|
| **Trigger** | Click `[Run sync now]` button (visible in empty state or sub-bar) |
| **Input** | None |
| **System response** | POST /pipeline/run — button becomes `[Syncing…]` + spinner. Last-sync timestamp updates when done. New cards appear when pipeline completes. |
| **Error state** | Pipeline errors surface as per-source failure signal on last-sync timestamp |
| **Exit state** | Pipeline complete. New cards (if any) in card stack. Last-sync updated. |

### Touchpoint 7 — CV override

| | |
|---|---|
| **Trigger** | Click `[▾ Use a different CV]` in expanded card |
| **Input** | Selected CV from dropdown |
| **System response** | PATCH /cards/{id}/cv — CV chip in expanded card updates. Override stored in DB. |
| **Error state** | API call fails: selection reverts, brief toast |
| **Exit state** | New CV shown as recommendation. Override persists on refresh. |

---

## Open UX Questions

1. **Card width**: full-width stack (single column) vs. two-column grid? Two columns would show more cards per viewport without scrolling, but makes keyboard navigation less linear. This spec assumes single-column. Confirm.
2. **`[Run sync now]` placement**: currently shown in empty state and as a small button in the sub-bar. Should it be more prominent in the header at all times, or only surface when the pipeline hasn't run recently?
3. **CV filenames**: user has 5 CVs. Are they already named with meaningful names (e.g., `CV-LLM.pdf`, `CV-Causal.pdf`) or should jd-matcher let the user label each CV with a short descriptor shown in the UI?
4. **Applied tab default sort**: this spec proposes oldest-first (most stale applications first). Alternative is newest-first (most recent applications at top). Which fits the user's review habit?
5. **`Business Analytics / BI` tag dimming**: this spec dims the chip visually (Stone colour) to signal the user typically avoids these roles. But the fit-score threshold already handles this. Does the user want an explicit visual dim for BI-heavy roles that still pass the threshold, or is ordering-by-score sufficient?
6. **Dismissed tab**: search-first layout. How often does the user expect to visit this tab? If "never except to debug", it could be a gear-icon modal rather than a top-level tab — reduces visual prominence of a rarely-used surface.

---

## Claude Design Brief

**Applicable**: Yes

**Brief**: `projects/jd-matcher/docs/discovery/designs/main-page-brief.md`
