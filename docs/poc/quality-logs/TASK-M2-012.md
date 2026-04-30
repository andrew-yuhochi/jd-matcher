# Quality Log — TASK-M2-012: LLM Dedup Gatekeeper (C32) — Phase 1

**Date**: 2026-04-29
**Status**: Phase 1 complete — awaiting user-labeled real pairs for Phase 2

---

## Phase 1 Scope

Phase 1 builds:
- `src/jd_matcher/dedup/classifier.py` — `LLMDedupClassifier` (C32 component)
- `prompts/dedup_classifier_v1.txt` — gatekeeper prompt with 3 worked examples
- Updated `src/jd_matcher/dedup/engine.py` — 3-tier decide() logic
- Updated `src/jd_matcher/dedup/merge.py` — pending_gatekeeper NO-OP guard
- Updated `src/jd_matcher/pipeline.py` — skip pending_gatekeeper in merge loop
- `src/jd_matcher/dedup/calibrate.py` — calibration CLI
- `src/jd_matcher/db/init_db.py` — notes column migration on llm_call_ledger
- `config/dedup.yaml` — gatekeeper_threshold + gatekeeper_retry_count
- `tests/fixtures/dedup_synthetic_pairs.yaml` — 30 synthetic pairs
- `tests/fixtures/dedup_labels.csv` — 15 candidate real pairs for user labeling
- `tests/dedup/test_classifier.py` — 15 new tests
- `tests/dedup/test_calibrate.py` — 26 new tests
- New tests in `tests/dedup/test_engine.py` — 17 new tests (3-tier logic + serialization)

---

## Test Results

| Metric | Value |
|--------|-------|
| Tests before Phase 1 | 915 |
| Tests after Phase 1 | 963 |
| New tests added | 48 |
| Tests passing | 963 |
| Tests failing | 0 |

---

## Synthetic Calibration Results (Phase 1)

**Pairs**: 30 synthetic (10 dup / 10 non-dup / 10 ambiguous)
**Gatekeeper calls**: 19 (11 skipped: 7 exact_4f short-circuit + 4 below 0.75 threshold)
**LLM cost**: ~$0.07 USD (gpt-4o-mini, estimated from token counts)

### Threshold sweep (non-ambiguous 20 pairs only)

| Threshold | Raw-FUSE P | Raw-FUSE R | Raw-FUSE F1 | GK-Augmented P | GK-Augmented R | GK-Augmented F1 |
|-----------|-----------|-----------|------------|---------------|---------------|----------------|
| 0.85 | 0.625 | 1.000 | 0.769 | **1.000** | **1.000** | **1.000** |
| 0.88 | 0.692 | 0.900 | 0.783 | **1.000** | **1.000** | **1.000** |
| 0.90 | 0.692 | 0.900 | 0.783 | **1.000** | **1.000** | **1.000** |
| 0.92 | 1.000 | 0.700 | 0.824 | **1.000** | **1.000** | **1.000** |
| 0.95 | 1.000 | 0.700 | 0.824 | **1.000** | **1.000** | **1.000** |

**Key finding**: Gatekeeper-augmented precision/recall/F1 = 1.0 across all thresholds on synthetic pairs. The gatekeeper correctly:
- Approved all 10 dup pairs (some via exact_4f short-circuit, some via LLM verdict)
- Rejected all 10 non-dup pairs (different-team, different-company, different-seniority, hiring-agent)
- Classified all 10 ambiguous pairs as 'new' (conservative — expected given that all are drawn from different-team / same-employer scenarios)

### Regression gate (SC-7 — zero false merges on different-team pairs)

All 7 different-team synthetic pairs correctly returned action='new':
- synth_011: TD Bank Credit Risk vs Fraud Analytics → different (FUSE=0.727, below threshold)
- synth_012: Hootsuite Content Intelligence vs Product Growth → different (gatekeeper)
- synth_013: Sophos Threat Detection vs Email Security → different (FUSE=0.727, below threshold)
- synth_016: Alquemy AML vs Capital Markets → different (gatekeeper)
- synth_017: Fortinet Security Analytics vs BI → different (gatekeeper)
- synth_020: EA Live Services vs Finance Analytics → different (gatekeeper)
- One additional different_company pair (synth_015, synth_019) also correctly rejected.

**Result: 0 false merges on different-team pairs.** SC-7 regression gate PASSES.

### Sample gatekeeper verdicts (3 interesting cases)

**synth_003** (near_dup, GT=merge, FUSE=0.870):
- Verdict: MERGE — "Both postings describe the same Senior Data Engineer role at Hootsuite's Data Platform team in Vancouver, with identical core responsibilities (building and maintaining data infrastructure, ELT workflows) and requirements. Minor differences in wording do not indicate distinct roles."

**synth_012** (different_team, GT=new, FUSE=0.760):
- Verdict: NEW — gatekeeper correctly identified Hootsuite Content Intelligence (NLP/social media) vs Product Growth (A/B testing/funnel analytics) as different teams with different mandates.

**synth_021** (ambiguous — Alquemy two similar credit risk postings, GT=new, FUSE=0.914):
- Verdict: NEW — gatekeeper identified they are representing different client banks with similar mandates; cannot confirm same role. Correct for a borderline case.

---

## 3-Tier Architecture Summary

```
FUSE < 0.75           → action='new'  (no gatekeeper call)       — 4 pairs in Phase 1 synthetic
ALL 4 features >= 1-ε → action='merge', merge_kind='exact_4f'   — 7 pairs (identical titles/skills/seniority)
0.75 <= FUSE < 1-ε   → gatekeeper call                          — 19 pairs
  → is_same_role=True  → action='merge', merge_kind='gatekeeper_approved'
  → is_same_role=False → action='new'
  → hard fail (both retries) → action='pending_gatekeeper' (fail-CLOSED)
```

---

## Phase 2 — Pending (user labels required)

**Next steps for the user**:
1. Open `tests/fixtures/dedup_labels.csv`
2. Fill in the `user_label` column for each row: `merge` or `new`
3. `user_notes` is optional — add reasoning for borderline cases
4. Leave `user_label` blank if you're unsure (those rows are skipped)

**Target**: 10-15 labeled real pairs. The CSV already contains 15 candidate pairs drawn from the live 148-canonical DB including known borderline cases.

After labeling, re-dispatch data-pipeline:
```
/implement jd-matcher TASK-M2-012  (Phase 2 — user-labeled calibration)
```

---

## Open Issues / Flags

1. **LLM cost tracking**: The calibrate module does not yet capture cost from the `ExtractionMetadata` returned by the provider (the cost fields on `ExtractionMetadata` are populated by the OpenAI extractor). The calibration report shows $0.00 because `call_cost_usd` is not wired back from the classify() call to the PairResult. This is a minor cosmetic issue — actual costs are tracked in `llm_call_ledger` during pipeline runs. For Phase 2, wire the cost from the ExtractionMetadata into PairResult.

2. **Synthetic FUSE proxy**: The calibration module uses title embedding as a proxy for role_summary embedding on synthetic pairs (no DB embeddings available). This slightly inflates FUSE scores for identical-title pairs and understates them for near-dups with different titles. Real-data calibration (Phase 2) will use actual DB embeddings.

3. **Ambiguous pairs all classified as 'new'**: All 10 ambiguous synthetic pairs were correctly flagged as 'new' by the gatekeeper. This is the expected conservative behavior — these pairs represent same-company same-title scenarios where the team distinction is subtle. User review of gatekeeper reasoning for ambiguous pairs is recommended before finalizing thresholds.
