# Claude Design Brief — jd-matcher / Main Page

> Paste this entire brief into Claude Design (claude.ai). Save the resulting prototype URL or PDF export to `projects/jd-matcher/docs/discovery/designs/main-page-prototype.<ext>` and link it back here.

## Surface

The daily triage view: a three-tab single-column web page showing ranked job posting cards that the user clears every morning in under a minute.

## Target user

A Vancouver-based senior Data Scientist / ML Engineer, job-hunting daily, opening this tool on a desktop browser (1440px+) and expecting Linear-grade polish — no decorative elements, maximum information density, zero onboarding copy.

## Primary goal of this surface

Let the user visually triage 5–20 job cards per day and act on each (expand, dismiss, or mark applied) without friction or confusion about which card is focused.

## Key information shown

- **Tab bar**: "Main (12)" | "Applied (5)" | "Dismissed" — counts as badges; Main is selected; settings gear right-aligned.
- **Sub-bar**: search input (`/` to activate), last-sync timestamp ("Last sync: 2 min ago" in muted text, amber if a source failed).
- **Card stack — collapsed state**: three lines per card — (1) coloured tag chip + bold title + em-dash + company name; (2) location · seniority · salary range in muted 13px; (3) industry · source count · posting age in subtle 12px. Action buttons (`Applied`, `Dismiss`) right-aligned on line 2, visible on hover. Keyboard focus shown as a 2px accent-coloured outline on the card.
- **Card stack — expanded state** (one card expanded inline): all secondary tags as outlined chips, CV recommendation name with 1-line rationale, "Use a different CV" disclosure, apply URL buttons per source, scrollable JD body (max 400px height), action row repeated at bottom.
- **Empty state**: centred text "No new postings today. Next sync in 47 minutes." with a small `[Run sync now]` button — no illustration.
- **Error banner**: amber/red persistent banner at top if Gmail is disconnected, with `[Reconnect Gmail]` CTA.

## Interactions

- Hover on collapsed card → action buttons fade in right-aligned.
- `j/k` keyboard focus moves between cards → outline moves to next/previous card.
- `e` → card expands in-place, pushing cards below down.
- `d` → card exits left (translate animation) and collapses, next card receives focus.
- `a` → card fades out, moves to Applied tab.
- `[▾ Use a different CV]` → compact dropdown showing 5 CVs with similarity bars (not numbers).

## Style & tone

- Tone: data-dense, keyboard-first, zero decoration. Think Linear, Attio, Height — not Notion, Trello, or any consumer app with rounded cards and pastel backgrounds.
- Background: near-black `#0F1117` or very dark navy `#111827`. Cards: `#1A1F2E` with `#252B3B` hover/focus. A dark theme is preferred — DS/ML engineers spend hours in dark IDEs.
- Accent: indigo `#6366F1` — used for keyboard focus ring, primary CTA buttons, active tab underline.
- Tag chip colours: violet for LLM/GenAI, blue for Traditional ML, teal for Experimentation, sky for NLP, rose for Applied Research, stone/grey for Business Analytics. White text on all filled chips.
- Typography: system sans-serif (Inter or -apple-system) for all text; monospace (JetBrains Mono or ui-monospace) for salary values only.
- Card border: 1px `#2E3347`. No drop shadows. Focus state: 2px `#6366F1` outline with `box-shadow: 0 0 0 3px rgba(99,102,241,0.2)`.
- Spacing: 8px base unit. Card padding: 16px horizontal, 12px vertical. Card gap: 8px. Max content width: 900px centred.
- Motion: dismiss = translateX(-100%) 180ms ease-in + height collapse 100ms. Mark-applied = opacity 0 150ms. Expand = height transition 200ms ease-out. All disabled if `prefers-reduced-motion`.

## Inspirations

- **Linear** (linear.app) — issue list density, dark theme, keyboard-first feel, tab navigation
- **Attio** (attio.com) — record card layout, field hierarchy, clean chip/badge treatment
- **GitHub pull request list** — action buttons on hover, status chips, muted secondary metadata

## Output requested

Interactive prototype with at least four states: (1) default Main tab with 4–5 collapsed cards, one card keyboard-focused; (2) one card expanded inline showing full JD + CV recommendation; (3) empty state for Main tab; (4) Applied tab with 2–3 cards showing status dropdowns and days counters.

---

## Resulting prototype

- Link: _to be filled by user after running Claude Design_
- Export: `projects/jd-matcher/docs/discovery/designs/main-page-prototype.<ext>`
