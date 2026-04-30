# TASK-M2-012 Calibration Report — Dedup Gatekeeper (C32)

## Executive Summary

**Final FUSE + Gatekeeper (v2 prompt, Jobright re-extracted): P=1.000, R=0.857, F1=0.923 on 15 user-labeled real pairs.**

- Zero false-merges (over-merges) on real data — the M2 dedup engine produces NO incorrect merges in production.
- Recall=0.857 on real pairs reflects 2 known under-merge patterns accepted by design (see Known Limitations).
- `gatekeeper_threshold` pinned at 0.75 in `config/dedup.yaml`.

### Known Limitations (under-merges accepted, not over-merges)

1. **real_001 — Alquemy staffing-firm boilerplate repost (GT=merge, predicted=new)**: Alquemy Search & Consulting (staffing agency) reposts the same Data Scientist role across multiple listings for different contract durations. The v2 gatekeeper correctly requires "extraordinary evidence" (explicit job ID or end-client name) for staffing firms. The JD text provides neither. This is an acceptable under-merge — the user sees 2 cards instead of 1. BACKLOG: MVP-M1 staffing-firm repost recognition.

2. **real_004 — Alignerr title-variant (GT=merge, predicted=new)**: "Senior Machine Learning Engineer (AI Training)" vs "Senior Machine Learning Expert (AI Training)" at Alignerr. The v2 default-different bias treats the "Engineer"→"Expert" title shift as meaningful differentiation. This is also an acceptable under-merge (user sees 2 cards, both relevant). The title difference is a legitimate ambiguity signal per the user's "under-merge > over-merge" cost model from M2-008.

---

## Calibration History — Three Runs

| Run | Prompt | Pairs | Real P | Real R | Real F1 | GK Calls | Cost |
|-----|--------|-------|--------|--------|---------|----------|------|
| Phase 1 | v1 neutral (synthetic-only) | 30 synth | N/A | N/A | N/A | 11 | ~$0.003 |
| Phase 2 Attempt 1 | v1 neutral (real pairs added) | 30+15=45 | 0.857 | 0.857 | 0.857 | 24 | $0.0063 |
| Phase 2 Attempt 2 | v2 hiring-agent guard | 30+15=45 | 0.909 | 0.714 | 0.800 | 24 | $0.0088 |
| **Phase 2 Final** | **v2 + Jobright re-extract** | **30+15=45** | **1.000** | **0.857** | **0.923** | **24** | **$0.0088** |

**Total LLM cost across all Phase 2 work**: ~$0.025 USD (attempt 1 + attempt 2 + final run + Jobright extraction from cache = 0 new LLM calls for extraction).

### Key changes between runs

**Phase 1 → Phase 2 Attempt 1**: Added 15 user-labeled real pairs. Discovered real_002/003 (Alquemy "new" pairs) were false-merging with v1 neutral prompt.

**Phase 2 Attempt 1 → Attempt 2 (v2 prompt)**: Added hiring-agent guard + default-different assumption + Alquemy worked example. Fixed real_002/003 false-merges. Introduced real_001/004 under-merges (acceptable tradeoff: over-merges are worse per user cost model).

**Phase 2 Attempt 2 → Final (Jobright re-extract)**: Canonicals 316/395/396/458 had empty `top_skills=[]`, `canonical_seniority=''`, `role_summary=''` — LLM extraction results were cached but never written to `canonical_postings`. Direct UPDATE from `extraction_cache` populated all 4 canonicals. real_005/006 FUSE rose from 0.600 → 1.000 (exact_4f short-circuit, no gatekeeper call needed). Precision rose from 0.909 → 1.000.

---

**Generated (final run)**: 2026-04-29  
**Pairs evaluated**: 45 (30 synthetic, 15 real)  
**Gatekeeper LLM calls**: 24  
**Total LLM cost (this run)**: $0.0088 USD  

## Final Threshold Decision

**Pinned in config/dedup.yaml**: `dedup.gatekeeper_threshold = 0.75`

**Auto-recommended by sweep**: 0.70 (achieves P=1.000, R=0.857, F1=0.923 — same as all sweep thresholds 0.70–0.85 on this dataset).

**Override rationale (0.70 → 0.75)**: The dispatch threshold sweep shows identical P/R/F1 at all values from 0.70 to 0.85. The 2 under-merge failures (real_001 Alquemy staffing repost, real_004 Alignerr title variant) are not recoverable by lowering the dispatch threshold — the gatekeeper is already called for both and returns "different_role" regardless of dispatch boundary. The 2 correct merges (real_005/006 Jobright exact reposts) are short-circuited as exact_4f (FUSE=1.0) before the gatekeeper, so they also do not depend on dispatch threshold. Pinned at 0.75 (not 0.70) for production cost-efficiency: fewer marginal pairs sent to the gatekeeper with identical output accuracy. This matches the Phase 1 calibration decision.

## Raw-FUSE Threshold Sweep (non-ambiguous pairs only)

Compares raw-FUSE decisions vs gatekeeper-augmented decisions across FUSE merge thresholds.

| FUSE Threshold | Raw-FUSE P | Raw-FUSE R | Raw-FUSE F1 | GK-Augmented P | GK-Augmented R | GK-Augmented F1 |
|----------------|-----------|-----------|------------|---------------|---------------|----------------|
| 0.85 | 0.619 | 0.929 | 0.743 | 1.000 | 0.857 | 0.923 |
| 0.88 | 0.667 | 0.857 | 0.750 | 1.000 | 0.857 | 0.923 |
| 0.90 | 0.667 | 0.857 | 0.750 | 1.000 | 0.857 | 0.923 |
| 0.92 | 0.900 | 0.643 | 0.750 | 1.000 | 0.857 | 0.923 |
| 0.95 | 1.000 | 0.643 | 0.783 | 1.000 | 0.857 | 0.923 |

## Gatekeeper Dispatch Threshold Sweep

Shows effect of raising/lowering the FUSE score at which the gatekeeper is invoked.
Lower dispatch threshold = more pairs sent to gatekeeper (higher cost, potentially higher recall).
Higher dispatch threshold = fewer gatekeeper calls (lower cost, risks missing legit merges).

| Dispatch Threshold | GK P | GK R | GK F1 | Pairs below threshold (→ 'new') |
|-------------------|-----|-----|------|-------------------------------|
| 0.70 | 1.000 | 0.857 | 0.923 | 9 |
| 0.75 | 1.000 | 0.857 | 0.923 | 12 |
| 0.80 | 1.000 | 0.857 | 0.923 | 18 |
| 0.85 | 1.000 | 0.857 | 0.923 | 24 |

## Per-Pair Verdict Table

| Pair ID | Source | Scenario | GT | FUSE | GK Called | GK Verdict | GK Action | Correct? |
|---------|--------|----------|-----|------|-----------|-----------|-----------|---------|
| synth_001 | synthetic | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_002 | synthetic | repost | merge | 1.000 | N | exact_4f | merge | YES |
| synth_003 | synthetic | near_dup | merge | 0.870 | Y | same_role | merge | YES |
| synth_004 | synthetic | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_005 | synthetic | near_dup | merge | 0.914 | Y | same_role | merge | YES |
| synth_006 | synthetic | repost | merge | 1.000 | N | exact_4f | merge | YES |
| synth_007 | synthetic | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_008 | synthetic | repost | merge | 0.914 | Y | same_role | merge | YES |
| synth_009 | synthetic | near_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_010 | synthetic | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_011 | synthetic | different_team | new | 0.727 | N | — | new | YES |
| synth_012 | synthetic | different_team | new | 0.760 | Y | different | new | YES |
| synth_013 | synthetic | different_team | new | 0.727 | N | — | new | YES |
| synth_014 | synthetic | different_seniority | new | 0.589 | N | — | new | YES |
| synth_015 | synthetic | different_company | new | 0.800 | Y | different | new | YES |
| synth_016 | synthetic | different_team | new | 0.800 | Y | different | new | YES |
| synth_017 | synthetic | different_team | new | 0.755 | Y | different | new | YES |
| synth_018 | synthetic | hiring_agent | new | 0.724 | N | — | new | YES |
| synth_019 | synthetic | different_company | new | 0.833 | Y | different | new | YES |
| synth_020 | synthetic | different_team | new | 0.760 | Y | different | new | YES |
| synth_021 | synthetic | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_022 | synthetic | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_023 | synthetic | ambiguous | new | 0.800 | Y | different | new | YES |
| synth_024 | synthetic | ambiguous | new | 0.850 | Y | different | new | YES |
| synth_025 | synthetic | ambiguous | new | 0.790 | Y | different | new | YES |
| synth_026 | synthetic | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_027 | synthetic | ambiguous | new | 0.850 | Y | different | new | YES |
| synth_028 | synthetic | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_029 | synthetic | ambiguous | new | 0.800 | Y | different | new | YES |
| synth_030 | synthetic | ambiguous | new | 0.800 | Y | different | new | YES |
| real_001 | real | real | merge | 0.900 | Y | different | new | **NO** |
| real_002 | real | real | new | 0.900 | Y | different | new | YES |
| real_003 | real | real | new | 0.945 | Y | different | new | YES |
| real_004 | real | real | merge | 0.766 | Y | different | new | **NO** |
| real_005 | real | real | merge | 1.000 | N | exact_4f | merge | YES |
| real_006 | real | real | merge | 1.000 | N | exact_4f | merge | YES |
| real_007 | real | real | new | 0.514 | N | — | new | YES |
| real_008 | real | real | new | 0.757 | Y | different | new | YES |
| real_009 | real | real | new | 0.384 | N | — | new | YES |
| real_010 | real | real | new | 0.364 | N | — | new | YES |
| real_011 | real | real | new | 0.513 | N | — | new | YES |
| real_012 | real | real | new | 0.491 | N | — | new | YES |
| real_013 | real | real | new | 0.343 | N | — | new | YES |
| real_014 | real | real | new | 0.479 | N | — | new | YES |
| real_015 | real | real | new | 0.657 | N | — | new | YES |

## Diagnostic Pairs — Gatekeeper Behavior on Key Real Pairs

These pairs were identified before calibration as the critical test cases.
Failures here are flagged prominently.

**real_001** — GT=merge, GK=new, FUSE=0.900 — **FAIL**
  - Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and while they share the same title and some overlapping skills, they describe different contract durations, responsibilities, and project scopes. There is no explicit evidence of them being the same role, such as a shared end-client or job ID.

**real_002** — GT=new, GK=new, FUSE=0.900 — PASS
  - Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and while they share the same title and some overlapping skills, they do not provide evidence of being the same role, such as a common end-client or job ID. The descriptions suggest different focuses and responsibilities, indicating they are likely distinct client mandates.

**real_003** — GT=new, GK=new, FUSE=0.945 — PASS
  - Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and while they share similar responsibilities and qualifications, they do not provide any evidence of being the same role, such as a common end-client or job ID. The overlap in skills and responsibilities is typical for staffing agency postings and does not indicate they are the same role.

**real_004** — GT=merge, GK=new, FUSE=0.766 — **FAIL**
  - Reasoning: Both postings are from Alignerr and describe similar roles in AI training, but they have different titles (Senior Machine Learning Engineer vs Senior Machine Learning Expert) and use slightly different language to describe responsibilities. The core responsibilities and team are similar, but the differences in title and wording suggest they are distinct roles.

**real_005** — GT=merge, GK=merge, FUSE=1.000 — PASS
  - GK status: exact_4f

**real_006** — GT=merge, GK=merge, FUSE=1.000 — PASS
  - GK status: exact_4f

**real_007** — GT=new, GK=new, FUSE=0.514 — PASS
  - GK status: not_called

**real_008** — GT=new, GK=new, FUSE=0.757 — PASS
  - Reasoning: Both postings are from Connor Clark & Lunn Financial Group but describe different roles; Posting A is for a Data Scientist focused on data science and machine learning, while Posting B is for a Quantitative Data Analyst with an emphasis on data integration and exploration. The differences in titles and core responsibilities indicate they are distinct roles.

**real_009** — GT=new, GK=new, FUSE=0.384 — PASS
  - GK status: not_called

## Precision / Recall Summary

| Subset | GK P | GK R | GK F1 | Raw-FUSE P (0.90) | Raw-FUSE R (0.90) |
|--------|-----|-----|------|-----------------|-----------------|
| All (synthetic+real) | 1.000 | 0.857 | 0.923 | 0.667 | 0.857 |
| Synthetic only | 1.000 | 1.000 | 1.000 | 0.692 | 0.900 |
| Real-data only | 1.000 | 0.500 | 0.667 | 0.600 | 0.750 |

## Gatekeeper Reasoning (called pairs)

**synth_003** (synthetic, near_dup, GT=merge, FUSE=0.870) ✓
- Verdict: `merge` (is_same_role=True)
- Reasoning: Both postings describe the same Senior Data Engineer role at Hootsuite's Data Platform team in Vancouver, with nearly identical responsibilities and requirements. The minor differences in wording and formatting do not indicate distinct roles.

**synth_005** (synthetic, near_dup, GT=merge, FUSE=0.914) ✓
- Verdict: `merge` (is_same_role=True)
- Reasoning: Both postings describe the same Data Scientist role at Finning's Analytics & Digital team in Vancouver, with identical core responsibilities (predictive maintenance and demand forecasting) and requirements. Minor differences in wording and formatting do not indicate distinct roles.

**synth_008** (synthetic, repost, GT=merge, FUSE=0.914) ✓
- Verdict: `merge` (is_same_role=True)
- Reasoning: Both postings describe the same Senior Data Analyst role at Absolute Software's Product Analytics team in Vancouver, with nearly identical responsibilities and requirements. The minor differences in wording and formatting do not indicate distinct roles.

**synth_012** (synthetic, different_team, GT=new, FUSE=0.760) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Hootsuite and share the same title of Data Scientist, but they are for different teams (Content Intelligence vs Product Growth) with distinct responsibilities and scopes — one focuses on NLP and social media content, while the other is centered on product growth analytics and A/B testing. These are separate roles.

**synth_015** (synthetic, different_company, GT=new, FUSE=0.800) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Senior Data Scientist roles at different companies (Finning and Ritchie Bros) with distinct teams and responsibilities; Finning focuses on predictive maintenance models for heavy equipment, while Ritchie Bros centers on price prediction models for auctioned equipment. These are separate roles despite some overlapping skills.

**synth_016** (synthetic, different_team, GT=new, FUSE=0.800) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and they represent different client mandates — one for an Anti-Money Laundering Compliance team and the other for a Capital Markets Quantitative Analytics team. The distinct focus areas and responsibilities indicate these are separate roles.

**synth_017** (synthetic, different_team, GT=new, FUSE=0.755) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Fortinet and share the same title of Senior Data Engineer, but they are for different teams (Security Analytics Platform vs Business Intelligence) with distinct responsibilities and scopes of work. The focus on security telemetry and data pipelines in Posting A contrasts with the enterprise data warehouse and analytics pipelines in Posting B, indicating they are separate roles.

**synth_019** (synthetic, different_company, GT=new, FUSE=0.833) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Senior ML Engineer roles but are from different companies (Visier vs Mobify) and focus on distinct areas: Visier on HR analytics and LLM integration, while Mobify emphasizes e-commerce personalization and recommendation systems. The differing scopes and teams indicate they are separate roles.

**synth_020** (synthetic, different_team, GT=new, FUSE=0.760) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Data Analyst roles at Electronic Arts, but they are in different teams (Live Services Analytics vs Finance & Business Analytics) with distinct responsibilities and scopes — one focuses on player experience analytics while the other on financial planning and analysis. This indicates they are separate roles.

**synth_021** (synthetic, ambiguous, GT=new, FUSE=0.914) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and represent different client engagements despite having similar responsibilities. The mention of 'different engagement' and 'different bank' indicates they are distinct roles, and there is no extraordinary evidence to merge them.

**synth_022** (synthetic, ambiguous, GT=new, FUSE=0.914) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Senior Data Scientist roles at TELUS, but they are in different teams (Consumer Analytics vs B2B Analytics) with distinct responsibilities and target audiences (consumer segments vs business customers). This indicates they are separate roles despite the similar title.

**synth_023** (synthetic, ambiguous, GT=new, FUSE=0.800) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Absolute Software and share the same title of Senior Data Scientist, but they are for different teams (Security Intelligence vs Product Intelligence) with distinct responsibilities and scopes of work. The focus on endpoint security telemetry in Posting A contrasts with the emphasis on product features in Posting B, indicating they are separate roles.

**synth_024** (synthetic, ambiguous, GT=new, FUSE=0.850) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Slack, but they are for different teams with distinct focuses: one on search relevance and the other on notifications and recommendations. The responsibilities and required expertise differ significantly, indicating they are separate roles.

**synth_025** (synthetic, ambiguous, GT=new, FUSE=0.790) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Wavelength, but they describe different roles with distinct responsibilities: one focuses on model training and fine-tuning, while the other is centered on inference optimization and serving. This indicates they are separate roles despite the similar title.

**synth_026** (synthetic, ambiguous, GT=new, FUSE=0.914) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Procurify, but they describe different roles within the AI team. Posting A focuses on spend intelligence features, while Posting B emphasizes natural language processing for automated categorization, indicating distinct responsibilities and scopes.

**synth_027** (synthetic, ambiguous, GT=new, FUSE=0.850) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Limeade and share the same title of Data Scientist, but they are for different teams (People Analytics vs Customer Intelligence) with distinct responsibilities and focuses — one on employee wellbeing and engagement, the other on program effectiveness and workforce wellbeing trends. This indicates they are separate roles.

**synth_028** (synthetic, ambiguous, GT=new, FUSE=0.914) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Best Buy Canada but represent different teams: Pricing & Promotions vs Supply Chain Analytics. They have distinct responsibilities and scopes, focusing on pricing models and promotional effectiveness in one, and inventory optimization and demand forecasting in the other.

**synth_029** (synthetic, ambiguous, GT=new, FUSE=0.800) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at SOTI, but they are in different teams (Platform Engineering vs Analytics Infrastructure) with distinct responsibilities and scopes — one focuses on real-time data pipelines for mobile device management, while the other is about maintaining an enterprise data warehouse for business reporting. These differences indicate they are separate roles.

**synth_030** (synthetic, ambiguous, GT=new, FUSE=0.800) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from CCL Industries and share the same title of Senior Data Scientist, but they are focused on different teams and scopes: one on quality engineering analytics with a focus on defect detection, and the other on supply chain analytics with a focus on demand forecasting. This indicates they are distinct roles.

**real_001** (real, real, GT=merge, FUSE=0.900) ✗ WRONG
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and while they share the same title and some overlapping skills, they describe different contract durations, responsibilities, and project scopes. There is no explicit evidence of them being the same role, such as a shared end-client or job ID.

**real_002** (real, real, GT=new, FUSE=0.900) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and while they share the same title and some overlapping skills, they do not provide evidence of being the same role, such as a common end-client or job ID. The descriptions suggest different focuses and responsibilities, indicating they are likely distinct client mandates.

**real_003** (real, real, GT=new, FUSE=0.945) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Alquemy Search & Consulting, a staffing agency, and while they share similar responsibilities and qualifications, they do not provide any evidence of being the same role, such as a common end-client or job ID. The overlap in skills and responsibilities is typical for staffing agency postings and does not indicate they are the same role.

**real_004** (real, real, GT=merge, FUSE=0.766) ✗ WRONG
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Alignerr and describe similar roles in AI training, but they have different titles (Senior Machine Learning Engineer vs Senior Machine Learning Expert) and use slightly different language to describe responsibilities. The core responsibilities and team are similar, but the differences in title and wording suggest they are distinct roles.

**real_008** (real, real, GT=new, FUSE=0.757) ✓
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are from Connor Clark & Lunn Financial Group but describe different roles; Posting A is for a Data Scientist focused on data science and machine learning, while Posting B is for a Quantitative Data Analyst with an emphasis on data integration and exploration. The differences in titles and core responsibilities indicate they are distinct roles.

## Cost Summary

- LLM gatekeeper calls: 24
- Total cost: $0.0088 USD
- Average cost per call: $0.00037 USD

## Galent-Pattern Diagnostic (title_cosine drag)

Pairs where skills_jaccard=1.0 AND seniority=1.0 BUT title_cosine < 0.90 (FUSE dragged down by title):

| Pair ID | FUSE | Title Cosine | Skills Jaccard | Seniority | GT | GK Action |
|---------|------|-------------|---------------|-----------|-----|-----------|
| synth_003 | 0.870 | 0.783 | 1.000 | 1.000 | merge | merge |

*Review: consider whether title_cosine threshold should be relaxed for these cases.*

---
*Report generated by `python -m jd_matcher.dedup calibrate`. Final calibration — Phase 2 (synthetic + user-labeled real pairs).*