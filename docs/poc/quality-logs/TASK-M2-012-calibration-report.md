# TASK-M2-012 Calibration Report — Dedup Gatekeeper (C32)

**Generated**: 2026-04-29  
**Pairs evaluated**: 30 (30 synthetic, 0 real)  
**Gatekeeper LLM calls**: 19  
**Total LLM cost**: $0.0000 USD  

## Threshold Sweep (non-ambiguous pairs only)

| FUSE Threshold | Raw-FUSE P | Raw-FUSE R | Raw-FUSE F1 | GK-Augmented P | GK-Augmented R | GK-Augmented F1 |
|----------------|-----------|-----------|------------|---------------|---------------|----------------|
| 0.85 | 0.625 | 1.000 | 0.769 | 1.000 | 1.000 | 1.000 |
| 0.88 | 0.692 | 0.900 | 0.783 | 1.000 | 1.000 | 1.000 |
| 0.90 | 0.692 | 0.900 | 0.783 | 1.000 | 1.000 | 1.000 |
| 0.92 | 1.000 | 0.700 | 0.824 | 1.000 | 1.000 | 1.000 |
| 0.95 | 1.000 | 0.700 | 0.824 | 1.000 | 1.000 | 1.000 |

**Recommended threshold**: `0.85` (highest GK-augmented F1 while maintaining recall ≥80% on true dups)

## Per-Pair Verdict Table

| Pair ID | Scenario | GT | FUSE | GK Called | GK Verdict | GK Action | Correct? |
|---------|----------|-----|------|-----------|-----------|-----------|---------|
| synth_001 | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_002 | repost | merge | 1.000 | N | exact_4f | merge | YES |
| synth_003 | near_dup | merge | 0.870 | Y | same_role | merge | YES |
| synth_004 | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_005 | near_dup | merge | 0.914 | Y | same_role | merge | YES |
| synth_006 | repost | merge | 1.000 | N | exact_4f | merge | YES |
| synth_007 | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_008 | repost | merge | 0.914 | Y | same_role | merge | YES |
| synth_009 | near_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_010 | exact_dup | merge | 1.000 | N | exact_4f | merge | YES |
| synth_011 | different_team | new | 0.727 | N | — | new | YES |
| synth_012 | different_team | new | 0.760 | Y | different | new | YES |
| synth_013 | different_team | new | 0.727 | N | — | new | YES |
| synth_014 | different_seniority | new | 0.589 | N | — | new | YES |
| synth_015 | different_company | new | 0.800 | Y | different | new | YES |
| synth_016 | different_team | new | 0.800 | Y | different | new | YES |
| synth_017 | different_team | new | 0.755 | Y | different | new | YES |
| synth_018 | hiring_agent | new | 0.724 | N | — | new | YES |
| synth_019 | different_company | new | 0.833 | Y | different | new | YES |
| synth_020 | different_team | new | 0.760 | Y | different | new | YES |
| synth_021 | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_022 | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_023 | ambiguous | new | 0.800 | Y | different | new | YES |
| synth_024 | ambiguous | new | 0.850 | Y | different | new | YES |
| synth_025 | ambiguous | new | 0.790 | Y | different | new | YES |
| synth_026 | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_027 | ambiguous | new | 0.850 | Y | different | new | YES |
| synth_028 | ambiguous | new | 0.914 | Y | different | new | YES |
| synth_029 | ambiguous | new | 0.800 | Y | different | new | YES |
| synth_030 | ambiguous | new | 0.800 | Y | different | new | YES |

## Gatekeeper Reasoning (called pairs)

**synth_003** (near_dup, GT=merge, FUSE=0.870)
- Verdict: `merge` (is_same_role=True)
- Reasoning: Both postings describe the same Senior Data Engineer role at Hootsuite's Data Platform team in Vancouver, with identical core responsibilities (building and maintaining data infrastructure, ELT workflows) and requirements. Minor differences in wording do not indicate distinct roles.

**synth_005** (near_dup, GT=merge, FUSE=0.914)
- Verdict: `merge` (is_same_role=True)
- Reasoning: Both postings describe the same Data Scientist role at Finning's Analytics & Digital team in Vancouver, with identical core responsibilities (predictive maintenance and demand forecasting) and requirements. Minor differences in wording and formatting do not indicate distinct roles.

**synth_008** (repost, GT=merge, FUSE=0.914)
- Verdict: `merge` (is_same_role=True)
- Reasoning: Both postings describe the same Senior Data Analyst role at Absolute Software's Product Analytics team in Vancouver, with identical core responsibilities (KPI tracking, A/B testing, SQL data models) and requirements. Minor differences in wording do not indicate distinct roles.

**synth_012** (different_team, GT=new, FUSE=0.760)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Data Scientist roles at Hootsuite, but they are in different teams (Content Intelligence vs Product Growth) with distinct responsibilities and scopes of work, focusing on NLP for social media content versus growth analytics for a SaaS platform.

**synth_015** (different_company, GT=new, FUSE=0.800)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Senior Data Scientist roles, but they are at different companies (Finning vs Ritchie Bros) and focus on distinct areas: predictive maintenance for heavy equipment at Finning versus price prediction for auctioned equipment at Ritchie Bros. This indicates they are separate roles.

**synth_016** (different_team, GT=new, FUSE=0.800)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for a Senior Data Scientist role at Alquemy Search & Consulting, but they are for different teams with distinct focuses: one is for the Anti-Money Laundering Compliance team and the other for the Capital Markets Quantitative Analytics team, each requiring different expertise and responsibilities.

**synth_017** (different_team, GT=new, FUSE=0.755)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for a Senior Data Engineer role at Fortinet, but they are in different teams (Security Analytics Platform vs Business Intelligence) with distinct scopes of work and responsibilities, focusing on security data pipelines versus enterprise data warehousing and analytics.

**synth_019** (different_company, GT=new, FUSE=0.833)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Senior ML Engineer roles, but they are at different companies (Visier vs Mobify) and focus on distinct areas: Visier on HR analytics and LLM integration, while Mobify centers on e-commerce personalization and recommendation systems. This indicates they are separate roles.

**synth_020** (different_team, GT=new, FUSE=0.760)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Electronic Arts, but they are in different teams (Live Services Analytics vs Finance & Business Analytics) with distinct responsibilities and scopes of work, focusing on player experience analytics versus financial planning and analysis.

**synth_021** (ambiguous, GT=new, FUSE=0.914)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for Senior Data Scientist roles, but they are for different banks and distinct teams (Retail Banking Risk vs Retail Credit Analytics), which indicates different scopes and responsibilities despite some similarities in the core tasks.

**synth_022** (ambiguous, GT=new, FUSE=0.914)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at TELUS, but they are in different teams (Consumer Analytics vs B2B Analytics) with distinct scopes of work focused on consumer vs business customers. The responsibilities and target audiences differ significantly, indicating they are separate roles.

**synth_023** (ambiguous, GT=new, FUSE=0.800)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for a Senior Data Scientist role at Absolute Software, but they are in different teams (Security Intelligence vs Product Intelligence) with distinct scopes of work and responsibilities, focusing on endpoint security telemetry versus product feature improvement.

**synth_024** (ambiguous, GT=new, FUSE=0.850)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Slack, but they are for different teams (Search Relevance vs Notifications & Recommendations) with distinct responsibilities and scopes of work related to search ranking versus notification personalization. These are separate roles despite sharing the same title.

**synth_025** (ambiguous, GT=new, FUSE=0.790)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Wavelength, but they focus on different aspects of ML engineering: Posting A is about model training and fine-tuning, while Posting B is centered on inference optimization and serving. These distinct scopes indicate they are separate roles.

**synth_026** (ambiguous, GT=new, FUSE=0.914)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Procurify, but they focus on different aspects of data science; Posting A emphasizes spend intelligence while Posting B has a stronger focus on natural language processing. Additionally, they are for different roles within the same team, indicating distinct responsibilities.

**synth_027** (ambiguous, GT=new, FUSE=0.850)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for a Data Scientist role at Limeade, but they are in different teams (People Analytics vs Customer Intelligence) with distinct responsibilities and focuses, such as employee engagement models versus customer wellbeing analytics. This indicates they are separate roles despite the similar title.

**synth_028** (ambiguous, GT=new, FUSE=0.914)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at Best Buy Canada, but they are in different teams (Pricing & Promotions vs Supply Chain Analytics) with distinct responsibilities and scopes of work, focusing on pricing models versus inventory optimization.

**synth_029** (ambiguous, GT=new, FUSE=0.800)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at SOTI, but they are in different teams (Platform Engineering vs Analytics Infrastructure) with distinct scopes of work: one focuses on real-time data pipelines for mobile device management, while the other centers on enterprise data warehousing and analytics pipelines. These differences indicate they are separate roles.

**synth_030** (ambiguous, GT=new, FUSE=0.800)
- Verdict: `new` (is_same_role=False)
- Reasoning: Both postings are for the same title at CCL Industries, but they are focused on different teams and scopes: Posting A is centered on quality engineering analytics with a focus on defect detection, while Posting B is about supply chain analytics with an emphasis on demand forecasting and inventory optimization. These distinct responsibilities indicate they are separate roles.

## Cost Summary

- LLM gatekeeper calls: 19
- Total cost: $0.0000 USD
- Average cost per call: $0.00000 USD

## Galent-Pattern Diagnostic (title_cosine drag)

Pairs where skills_jaccard=1.0 AND seniority=1.0 BUT title_cosine < 0.90 (FUSE dragged down by title):

| Pair ID | FUSE | Title Cosine | Skills Jaccard | Seniority | GT | GK Action |
|---------|------|-------------|---------------|-----------|-----|-----------|
| synth_003 | 0.870 | 0.783 | 1.000 | 1.000 | merge | merge |

*Review: consider whether title_cosine threshold should be relaxed for these cases.*

---
*Report generated by `python -m jd_matcher.dedup calibrate`. Preliminary synthetic-only run.*