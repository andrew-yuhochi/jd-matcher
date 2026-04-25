# UX Specification — jd-matcher — PoC

> **Author**: ux-designer
> **Date**: 2026-04-24
> **Phase**: PoC (M1–M4)
> **Inherits from**: `docs/discovery/UX-SPEC.md` — read that document first for rationale. This spec narrows scope to PoC and adds implementable specificity.
> **Design brief (visual treatment)**: `docs/discovery/designs/main-page-brief.md` — unchanged for PoC. No new brief needed unless M4 analytics view warrants one (see §4).

---

## Purpose of this document

The discovery UX-SPEC covered the full product vision. This document:

1. Specifies what the UI looks like at the end of each milestone.
2. Finalises decisions deferred at discovery (Dismissed tab, CV management, analytics view, keyboard shortcuts).
3. Defines PoC-specific error and loading states.
4. Lists what the PoC explicitly does NOT have.

---

## 1. Milestone-Aware UI Progression

Each milestone adds a layer on top of the previous. The shell (tabs, sub-bar, search, settings gear) is present from M1.

### M1 — End state

Cards: title, company, location, source badge (text only: "LinkedIn", "Indeed"), apply URL, `[Mark Applied]` and `[Dismiss]` buttons. No fit score, no tag chips, no salary field, no CV chip. Placeholder slots for tags and CV chip are NOT rendered — their absence is expected at this milestone.

| UI element | State at end of M1 |
|---|---|
| Three tabs (Main / Applied / Dismissed) | Visible. Main has badge count. Dismissed has no count. |
| Card line 1 | Title — Company (bold). No tag chip. |
| Card line 2 | Location · Source (text) · Apply URL label |
| Card line 3 | First seen: "Today" or relative date |
| Tag chip slot | Absent — not rendered |
| Salary slot | Absent — not rendered |
| CV chip slot | Absent — not rendered |
| Action buttons | `[Mark Applied]` `[Dismiss]` — hover or keyboard focus |
| Dismissed tab | Visible tab. Shows search box first, then flat card list. "Restore to Main" per card (see §2). |
| Pipeline trigger | `[Run sync now]` button in sub-bar and in empty state |
| Source health badges | Sub-bar shows one badge per active source (LinkedIn email, Indeed email, LinkedIn hydrator, Indeed hydrator). Green / amber / red. Non-dismissible. Failure reason on hover. Auto-clears only when source returns healthy on next run. |
| JD hydration indicator | Cards whose hydration failed show a small inline indicator on line 2: `⚠ JD incomplete` (muted amber, 11px). Tooltip: "JD hydration incomplete — open at source for full description". All keyboard shortcuts (`d`, `a`, `o`) remain active on these cards. |
| Events | `card_viewed`, `card_dismissed`, `card_marked_applied` written to events table — no UI display yet |

Applied tab at M1: shows title, company, location, status dropdown (`Applied` → `Screen` → `Interview` → `Offer` → `Rejected` → `Ghosted`), "Applied N days ago", "Removes in N days", inline notes field. Full per discovery UX-SPEC.md §7.

### M2 — End state (incremental on M1)

| UI element | Change |
|---|---|
| Source badges on card | When a posting spans multiple sources: "2 sources" badge replaces single source label. Expanded card shows "Sources: LinkedIn · Himalayas" text list with per-source apply links. |
| Repost badge | Cards where `first_seen` is > 7 days before `last_seen` for the same canonical record show a subtle "Reposted" badge on line 3 (muted, 11px, no fill chip — plain text with a dot prefix). |
| Canonical-keyed state | Dismissing one source's card suppresses all matched variants — no visible change to UI affordance, but behaviour is now content-aware. |

No new UI controls at M2. The merge and repost indicators are read-only signals.

### M3 — End state (incremental on M2)

| UI element | Change |
|---|---|
| Primary tag chip | Now present on line 1, left-anchored, filled, colour per discovery UX-SPEC.md §6 palette. |
| Secondary tags | Visible in expanded card as outlined chips. |
| Salary | Appears on line 2 in monospace: `$140k–$180k CAD`. If not extracted: italic muted `Salary not listed`. |
| Industry badge | Line 3, plain muted text. |
| Card ordering | Soft-rank composite score (salary + industry + recency). Invisible to user — position only. |
| Fit score | Not shown. Below-threshold postings simply absent from Main (stored in DB, hedge 1). |
| Processing cards | Cards pending LLM classification show `[Processing…]` in tag position, no salary, no industry. They appear below fully-processed cards. |

### M4 — End state (incremental on M3)

| UI element | Change |
|---|---|
| CV chip | Appears in collapsed card: `CV: CV-LLM.pdf` (small chip, after salary on line 2, or own line 3 if space requires — implementer's call within density target). |
| CV expanded section | Full section per discovery UX-SPEC.md §5: top-1 rationale + similarity bars override dropdown for all 5. |
| `c` key | Copies recommended CV filename to clipboard. "Copied" toast (1.5s). Active only post-M4. |
| Settings page | `/settings` live. Gmail status, 5 CV path inputs, last-run timestamp, OpenAI key (see §3). |
| Analytics page | `/analytics` live (see §4). |
| Nav | Analytics icon (small chart icon, top-nav right of tabs, left of settings gear) links to `/analytics`. |

---

## 2. State-Management UX — Dismissed Tab

**Decision: Dismissed tab is a visible top-level tab from M1.** Discovery notes proposed "search-only" access; this is revised for PoC.

**Rationale**: this is a single-user personal tool. The user will occasionally accidentally dismiss a card or want to verify the blacklist during PoC calibration. A visible tab costs zero implementation overhead beyond what M1 already builds, and removes the need to invent a search-discovery path for a rarely-used surface. The tab has no badge count (permanently dimmed label) to signal it is not a daily-use surface.

**Dismissed tab layout**:

```
[ Search dismissed postings... ]
─────────────────────────────────
[card] [card] [card]  ← flat list, collapsed only, no expand
```

- Search box is first. This is NOT a daily-triage surface — the search makes the intent clear.
- Cards in Dismissed tab are collapsed-only. No expand, no apply, no status.
- Each card has a single action: `[Restore to Main]`.

**"Restore to Main" action:**

| | |
|---|---|
| **Trigger** | Click `[Restore to Main]` button on a Dismissed card |
| **Input** | Canonical posting ID |
| **System response** | POST /cards/{id}/restore — removes from dismissed blacklist, re-adds to Main view. Card disappears from Dismissed tab. Confirmation toast: "Restored to Main" (2s). |
| **Error state** | API failure: button restores to active state, toast "Restore failed". |
| **Exit state** | Posting reappears in Main on next render. |

**Keyboard shortcut for Dismissed tab**: `3` switches to Dismissed tab per the shortcut scheme. Once on Dismissed tab, `j/k` navigate the list, but `d/a/e` are inactive (cards cannot be acted on from Dismissed). Only mouse/click action `[Restore to Main]` is available.

**No undo on dismiss from Main**: the Dismissed tab IS the recovery mechanism. The user can restore within seconds of an accidental dismiss. A separate in-place undo toast would duplicate this.

---

## 3. CV Management UX (Settings Page)

The settings page lives at `/settings`, accessible via the gear icon top-right. PoC scope is minimal.

### Settings page layout

```
┌──────────────────────────────────────────────────────────────┐
│  jd-matcher  [Main] [Applied] [Dismissed]      [≡ Analytics] [⚙]  │
│──────────────────────────────────────────────────────────────│
│  Settings                                                    │
│                                                              │
│  Gmail                                                       │
│  ─────────────────────────────────────────────────          │
│  Connected: job-search@gmail.com           [Reconnect]       │
│  (or) Not connected.                       [Connect Gmail]   │
│                                                              │
│  OpenAI API key                                              │
│  ─────────────────────────────────────────────────          │
│  [sk-••••••••••••••••••]                   [Update]          │
│  (shown masked; user pastes new key to update)               │
│                                                              │
│  CV Variants                                                 │
│  ─────────────────────────────────────────────────          │
│  Each CV is a local file path. jd-matcher reads and          │
│  embeds the file at startup.                                 │
│                                                              │
│  CV 1  Nickname: [LLM & GenAI         ]                      │
│         Path:     [/Users/you/CVs/cv-llm.pdf          ]      │
│         Purpose:  [RAG, agents, LLM application roles  ]     │
│                                                              │
│  CV 2  Nickname: [Traditional ML      ]                      │
│         Path:     [/Users/you/CVs/cv-ml.pdf            ]     │
│         Purpose:  [Tabular ML, feature engineering     ]     │
│                                                              │
│  CV 3  ...  (slots 3–5 identical)                            │
│                                                              │
│  [Save CV changes]   (triggers re-embedding on save)         │
│                                                              │
│  Pipeline                                                    │
│  ─────────────────────────────────────────────────          │
│  Last run:   2026-04-24 07:42 AM    (read-only)              │
│  Schedule:   Hourly (from config)   (read-only)              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### CV field spec

| Field | Type | Max length | Notes |
|---|---|---|---|
| Nickname | Text input | 30 chars | Shown in card CV chip and override dropdown |
| Path | Text input | 260 chars | Local filesystem path, not validated until save |
| Purpose | Text input | 100 chars | Used in rationale generation template ("highest cosine match — [purpose]") |

**Save behaviour**: `[Save CV changes]` button triggers:
1. Validate all paths exist on filesystem. If a path does not exist: inline error below that input "File not found at this path."
2. If validation passes: re-embed all CVs that changed. Show "Embedding CVs… (2/5)" progress text next to the button. On complete: "Saved." (no toast — user is already on settings page).
3. No partial save — all CVs saved atomically.

**Adding/removing CVs**: PoC has exactly 5 slots, always visible. Slots with empty path/nickname are ignored at embedding time. No add/remove UI — the 5-slot fixed layout is intentional PoC simplicity.

**OpenAI API key**: stored in local `.env`. Settings page shows masked value. `[Update]` opens an inline text field; user pastes and saves. Key is written to `.env` (never shown in full in UI after save).

**Not in PoC settings** (inheriting from discovery UX-SPEC.md §9):
- Soft-rank weight sliders
- Fit-score threshold slider
- Tag taxonomy editor
- Pipeline schedule editing

---

## 4. Analytics View (M4 surface)

### Decision: FastAPI HTML page at `/analytics`, table-heavy, no charting library

**Rationale**: the analytics view is not a daily-use surface — it exists to (a) verify the events pipeline is working, and (b) produce Beta Gate 1 evidence (≤5 min/day median triage time). A Streamlit-style or React charting view adds a build-time dependency for a surface the user opens once per week at most. A FastAPI Jinja2 HTML template with an HTML table and a few `<pre>`-rendered numbers keeps the surface zero-dependency, always consistent with the FastAPI app, and visually sufficient for its purpose.

Charts are not needed. The user is a Data Scientist — a table of numbers is readable without a bar chart.

### Analytics page layout

```
┌──────────────────────────────────────────────────────────────┐
│  jd-matcher  [Main] [Applied] [Dismissed]      [≡ Analytics] [⚙]  │
│──────────────────────────────────────────────────────────────│
│  Analytics                                    [Last 7 days ▾] │
│                                                              │
│  Session summary                                             │
│  ─────────────────────────────────────────────────          │
│  Sessions (last 7d)       12                                 │
│  Median time-to-clear     3m 24s                             │
│  Fastest session          0m 47s                             │
│  Slowest session          8m 12s                             │
│                                                              │
│  Daily breakdown                                             │
│  ─────────────────────────────────────────────────          │
│  Date          Cards seen  Dismissed  Applied  Time (min)    │
│  2026-04-24    8           6          1        2:34          │
│  2026-04-23    14          11         2        4:12          │
│  ...                                                         │
│                                                              │
│  Source breakdown                                            │
│  ─────────────────────────────────────────────────          │
│  Source              Postings (7d)  Unique (not deduped)     │
│  LinkedIn            42             31                       │
│  Indeed              18             12                       │
│  Himalayas           11             9                        │
│  Remotive            4              4                        │
│  Job Bank Canada     3              3                        │
│  Jobicy              2              2                        │
│  HN Hiring           1              1                        │
│                                                              │
│  Events log (last 50)                                        │
│  ─────────────────────────────────────────────────          │
│  [Timestamp]  [Event]           [Posting ID]  [Duration]     │
│  07:43:12     card_viewed       abc123        —              │
│  07:43:18     card_expanded     abc123        6s             │
│  07:43:29     card_dismissed    abc123        —              │
│  ...                                                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Analytics data model

Data pulled from the `events` table (populated from M1). All queries filter by `user_id = 'default'` (hedge 3).

| Metric | Derivation |
|---|---|
| Session | Group consecutive events within 30-minute idle window |
| Time-to-clear | Time between first `card_viewed` event and last `card_dismissed` or `card_marked_applied` in a session |
| Dismiss rate | `card_dismissed` count / `card_viewed` count per session |
| Apply rate | `card_marked_applied` count / `card_viewed` count per session |
| Source contribution | Distinct canonical posting IDs sourced from each origin per week |

### Time-range filter

Dropdown: "Last 7 days" (default), "Last 30 days", "All time". Changes all three tables on page reload (no live AJAX — page reload is fine for a rarely-used surface).

### No Claude Design brief for analytics

The analytics page is table-heavy, minimal, and has low visual risk — wrong layout cannot invalidate the project concept. The main-page brief (`docs/discovery/designs/main-page-brief.md`) remains the single Claude Design artefact for PoC. The analytics page is implementer-discretion HTML table styling consistent with the main page's dark theme and type scale.

---

## 5. Loading and Error States — PoC Specifics

Inherits base states from discovery UX-SPEC.md §8. This section adds PoC-specific details.

### "Run sync" button states

| State | Button label | Sub-bar text |
|---|---|---|
| Idle | `[Run sync now]` | "Last sync: 2 min ago" |
| Running | `[Running…]` (disabled, spinner) | `Fetching Gmail… (step 1/4)` |
| Step 2 | — (same) | `Hydrating JDs… (2/4)` |
| Step 3 | — (same) | `Classifying (12/20)… (3/4)` |
| Step 4 | — (same) | `Ranking… (4/4)` |
| Done | `[Run sync now]` (re-enabled) | "Last sync: just now" |
| Failed | `[Run sync now]` (re-enabled) | "Last sync: failed — see log ↓" (amber text) |

Step count and card count are approximations from the pipeline — exact string format is implementer's call as long as it conveys the four stages.

### Per-source health badges (persistent, non-dismissible)

The sub-bar carries one badge per active source. Badges are always visible — there is no dismiss control. The user cannot hide them. A badge auto-clears only when the source returns healthy on the next pipeline run.

| Badge colour | Meaning |
|---|---|
| Green | Source fetched successfully on last run |
| Amber | Source returned a partial result or a recoverable error (e.g. rate-limited, 0 items but reachable) |
| Red | Source failed entirely — fetch could not complete |

Badge layout (sub-bar, right of "Last sync" timestamp):

```
Last sync: 2 min ago   [LI-email ●] [IN-email ●] [LI-hydrate ●] [IN-hydrate ●]
```

- Source labels are abbreviated: `LI-email`, `IN-email`, `LI-hydrate`, `IN-hydrate`.
- Hover / focus on a badge reveals a tooltip with the failure reason (e.g., "linkedin.com returned 429 — will retry next run").
- On a fully healthy run, all four badges are green; tooltip confirms "Fetched OK — N items".
- Badge colour persists across page reloads until the next pipeline run writes new health state.

### Pipeline failure — collapsible log panel

On failure: sub-bar timestamp turns amber with "see log ↓" link. Clicking link reveals a collapsible panel directly below the sub-bar (not a modal — modal blocks the card stack):

```
▼ Last sync error log (2026-04-24 07:43)
─────────────────────────────────────────────
[07:43:11] Step 1 (Gmail): OK — 3 new emails parsed
[07:43:44] Step 2 (Hydration): FAILED — linkedin.com returned 429
[07:43:44] Partial run: 3 emails ingested, 0 hydrated.
           Stored URLs will retry on next run.
─────────────────────────────────────────────
```

Panel is dismissible (click ▲ or click outside). Persists between page refreshes until a successful run replaces it.

### Card-level JD hydration indicator

Cards whose JD hydration failed are NOT dropped from the card list — they appear in their normal position with all triage affordances intact (`d`, `a`, `o` shortcuts all active).

An inline indicator appears on line 2, between location and source badge:

```
Senior ML Engineer — Acme Corp
Vancouver · Indeed  ⚠ JD incomplete  · apply.example.com
First seen: Today
```

- `⚠ JD incomplete` — muted amber, 11px, plain text with warning glyph. Not a chip or badge — just text.
- Tooltip on hover/focus: "JD hydration incomplete — open at source for full description."
- Indicator is informational, not alarming. The card is fully usable; the user simply has less text to read before deciding.
- Indicator clears automatically if hydration succeeds on a subsequent run.

### Gmail OAuth unauthenticated

Persistent amber banner at page top (below tab bar, above sub-bar):

```
! Gmail is not connected — LinkedIn, Indeed, and Job Bank emails won't be ingested.
  [Connect Gmail]
```

Non-blocking: API sources (Himalayas, Remotive, Jobicy, HN) continue to work. Banner does not auto-dismiss after connecting — page reload clears it once OAuth is confirmed.

### OpenAI API key missing

Persistent amber banner (same slot as Gmail banner, stacks below if both active):

```
! OpenAI API key is not configured — LLM extraction and CV embedding unavailable.
  [Configure]   ← links to /settings#openai
```

M1 and M2 (pre-classification) are unaffected. M3 onwards: banner blocks smart-layer features but does not block ingestion or state management.

### No new postings (PoC version — pre-dismissal-learning)

```
No new postings found.
Your saved searches may need widening, or all recent postings were already seen.
[Run sync now]
```

Distinct from the first-run empty state (which says "First results should appear within 60 minutes"). After the first run has completed at least once, the above copy applies.

---

## 6. Keyboard Shortcuts — PoC Final

Inheriting from discovery UX-SPEC.md §4. All shortcuts below are locked for PoC implementation.

| Key | Action | Notes |
|---|---|---|
| `j` / `↓` | Focus next card | 2px accent outline on focused card |
| `k` / `↑` | Focus previous card | |
| `e` | Toggle expand / collapse focused card | Second `e` collapses |
| `d` | Dismiss focused card | Slide-left animation (180ms) then collapse (100ms). Focus moves to next card. |
| `a` | Mark applied | Fade-out animation (150ms). Focus moves to next card. |
| `o` | Open first apply URL in new tab | `Shift+o` opens all source URLs |
| `c` | Copy recommended CV filename | Active post-M4 only. "Copied" toast (1.5s). No-op pre-M4. |
| `1` | Switch to Main tab | |
| `2` | Switch to Applied tab | |
| `3` | Switch to Dismissed tab | |
| `/` | Focus search input | `Esc` returns focus to card list |
| `?` | Show keyboard shortcut cheatsheet | Modal, `Esc` to close |
| `Esc` | Priority: close cheatsheet → collapse expanded card → blur search | |

**No changes from discovery.** The scheme is already optimised for the single-user daily-triage goal.

**Shortcut behaviour on Dismissed tab**: `j/k` navigate, but `d`, `a`, `e`, `o`, `c` are inactive. Only mouse interaction (`[Restore to Main]`) works on Dismissed. This is intentional — Dismissed is not a triage surface.

**Cheatsheet**: modal opened by `?`. Two-column table listing key → action. Post-M4 note: `c` labelled "(available after first CV is configured)". `Esc` closes. No prose.

---

## 7. What the PoC UI Explicitly Does NOT Have

Inheriting from discovery UX-SPEC.md "What NOT to Build", with PoC-specific additions:

| Not built | Deferred to |
|---|---|
| Dismissal-reason category dropdown | MVP |
| Dismissal-learning weekly review surface | MVP |
| Fit score badge on any card | Never (by design — position communicates rank) |
| Threshold sliders (fit, dedup, rank weights) | MVP settings |
| Fit-score threshold visible in UI | Config file only in PoC |
| Tag taxonomy editor | MVP |
| French-language toggle | MVP |
| Bulk select / bulk dismiss | Never (volume is too low) |
| Inline CV editing or rewriting | Never (out of scope, §14 DISCOVERY-NOTES.md) |
| Push notifications | Never |
| Mobile layout | Never (PoC) |
| Undo on `[Mark Applied]` | Not needed — Applied tab status dropdown allows correction |
| "Possible duplicate" hint on cards | MVP (per DISCOVERY-NOTES.md §5) |
| Cross-location dedup pass | MVP |
| Soft-rank weight sliders in settings | MVP |
| Local-vs-cloud LLM benchmark UI | Optional sub-task at M3 only if user opts in; not a default surface |
| Analytics charts / visualisations | Never in PoC — HTML table is sufficient |

---

## 8. Open Questions for User Decision at /milestone-plan

The following require a user decision before milestone implementation begins. They are not blockers for writing TASKS.md but should be resolved at M1 kickoff.

| # | Question | Default assumption (if not answered) |
|---|---|---|
| OQ-1 | Should the CV chip appear on its own line 3 in the collapsed card (cleaner), or appended to line 2 after salary (denser)? | Own line 3 — consistent with 70px card height target |
| OQ-2 | Analytics time-range filter: page reload on selection, or AJAX in-place refresh? | Page reload — simpler, low-traffic surface |
| OQ-3 | The discovery UX-SPEC §11 left "card width" open (single-column vs. two-column). Single-column is assumed here. Confirm. | Single column — keyboard navigation is linear and simpler |
| OQ-4 | `[Run sync now]` placement: always visible in sub-bar, or only in empty state? | Always visible in sub-bar as small text button; larger in empty state |
| OQ-5 | Should the Analytics nav icon appear in M1 (linking to a placeholder) or only activate in M4? | Only active/visible in M4 to avoid a broken link during M1-M3 |

---

## Document References

- Discovery UX-SPEC (rationale and full interaction specs): `docs/discovery/UX-SPEC.md`
- Design brief (visual treatment, dark theme, type scale): `docs/discovery/designs/main-page-brief.md`
- Milestone acceptance criteria: `docs/discovery/ROADMAP.md`
- Product requirements: `docs/discovery/DISCOVERY-NOTES.md`
