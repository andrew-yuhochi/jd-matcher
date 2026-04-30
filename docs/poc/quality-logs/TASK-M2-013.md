# TASK-M2-013 — M2 Demo + User Approval

**Closed**: 2026-04-29
**Approver**: User (explicit "approve" reply at /milestone-complete prompt)

## Demo flow executed

User reviewed the live UI iteratively as the M2 deliverables shipped (chronological):

1. TASK-M2-014 (commit 7ea5674) — card UI enrichment validated; surfaced bugs (duplicate Apply buttons, missing canonical_id chip) → fix-forward 807eef3
2. TASK-M2-015 (commit 4cb7a36) — 5-line collapsed-card layout reshuffle validated
3. TASK-M2-015 follow-up (commit be1cc59) — role_summary in full per user feedback
4. TASK-M2-016 (commit 3ea1b79) — skills tiering validated; 1199 chips rendered correctly across 148 cards
5. TASK-M2-012 (commits 31a54fc + 962cf05) — LLM dedup gatekeeper + calibration; user-labeled 15 real pairs; final P=1.000 / R=0.857 / F1=0.923 explicitly approved
6. Tab count badge fixes (commits 93a167e + 6de087f) — live count updates + cross-page consistency validated

## Live observations

- Live DB: 148 canonical postings (LinkedIn-only per ALIGNMENT-LOG 2026-04-28)
- 8 confirmed merges visible with `2 variants` badges + correct apply links per posting
- Skills tiering: matching purple/blue/green chips; non-matching as gray "Other"; `Skills match: X/Y` footer accurate
- Tab badges: Main 148 / Applied 0 / Dismissed 0 (start state); decrement/increment on apply/dismiss/restore/unapply verified across all 3 tabs
- All keyboard shortcuts (j/k/e/d/a/o/O) functional on canonical-id-keyed cards

## ROADMAP §M2 ACs verification

| AC | Status | Evidence |
|---|---|---|
| ≥90% accuracy on 30 hand-labeled pairs | PASS | M2-012 calibration P=1.000, R=0.857, F1=0.923 |
| ZERO false-merges on different-team cases | PASS | SC-7 regression gate held in M2-012 calibration |
| Cross-source merge verified | PASS (synthetic) | Synthetic C21 fixtures from M2-008 + M2-012; LinkedIn-only PoC per PRD §9 R3 |
| State inheritance: dismissing one suppresses canonical | PASS | Live demo verification + apply-one-suppress-all unit tests |
| Repost detection: ≥3 cases | PASS (synthetic) | M2-009/010 synthetic; no real reposts in current corpus |
| Auto-merge threshold calibrated and recorded | PASS | config/dedup.yaml::dedup.gatekeeper_threshold = 0.75 pinned |

## Known limitations carried into MVP

Documented in BACKLOG.md (commits 5eac3a4, 68440bc):
- Staffing-firm repost recognition under-merge pattern (Alquemy real_001 case)
- extraction_cache → canonical_postings propagation gap (audit needed)
- Indeed extraction (deferred from PoC scope)
- 2-pane master-detail UX bundle + pagination + search + filter
- Architecture + test-suite review (pre-next-milestone hygiene pass)

## Approval

User reply: **approve** (verbatim, 2026-04-29).
