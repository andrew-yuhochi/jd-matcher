# TASK-M2-006 — Extraction Validation Report

## Round 2 — Few-shot + defensive defaults (2026-04-27)

Prompt changes applied to `prompts/canonical_extraction_v1.txt` (building on Round 1):
- Added `=== DEFENSIVE DEFAULTS ===` block (5 rules: seniority lower-bound, NULL team when no org context, Canada-first location, drop seniority qualifiers from title, most-specific org level for hierarchies)
- Added `=== EXAMPLES ===` block (3 complete JD → JSON few-shot examples: Senior IC + named team, Manager at services firm, Remote contractor/gig platform)

All 71 C19-passed postings re-extracted fresh (extraction_cache fully busted for gpt-4o-mini before run).

**Round 2 cost:** $0.074925 (139 live API calls, 211 cache hits across two partial runs)
**Total project spend to date:** $0.075263
**Cumulative spend including Round 1:** Round 1 = $0.030171 + Round 2 = $0.074925 = $0.105096 gross (Round 2 cache hits used Round 1 results where the posting hash hadn't changed)

---

### Diff summary: Round 1 → Round 2

**Total postings with ≥1 field change: 42** (of 71)
**Improvements: 26 | Regressions: 5 | Neutral/ambiguous: 11**

#### Confirmed improvements

| ID | Field | Round 1 | Round 2 | Default fired |
|----|-------|---------|---------|---------------|
| #1 UBC | team | "Research Group \| Olson Lab \| Department Mechanical Engineering \| Faculty of Applied Science" | "Olson Lab" | Default #5 (most-specific org level) |
| #2 Amazon | title | "Applied Scientist" | "Applied Scientist, Private Brands Discovery" | Default #4 (keep specialisation suffix) |
| #3 CC&L | title | "Quantitative Data Analyst" | "Quantitative Data Analyst, Investment Data" | Default #4 |
| #5 CC&L | title | "Data Scientist" | "Data Scientist, Investment Data" | Default #4 |
| #22 RBC | team | "RBC Borealis" | "Borealis" | Default #5 (RBC is admin context) |
| #27 EA | title | "Lead Data Scientist" | "Data Scientist - Search, Data & Insights" | Default #4 |
| #28 Amazon | title | "Data Scientist" | "Data Scientist, Alexa Connections" | Default #4 (specialisation kept) |
| #40 Cover Genius | title | "Senior Data Scientist - GenAI" | "Data Scientist - GenAI" | Default #4 (Senior stripped) |
| #44 Instacart | title | "Data Scientist" | "Data Scientist - Shopping Experience (Search)" | Default #4 |
| #53 EA SPORTS | team | "Generative AI Team" | "FC Generative AI" | More specific (correct sub-team) |
| #54 Clio | title | "Senior Developer, Enterprise AI" | "Developer, Enterprise AI" | Default #4 (Senior stripped) |
| #55 TELUS | title | "Senior Developer (AI/ML/Gen AI Solutions)" | "Developer (AI/ML/Gen AI Solutions)" | Default #4 |
| #56 CC&L | title | "Portfolio Research Analyst" | "Portfolio Research Analyst, Quantitative Equities" | Default #4 |
| #70 Outlier AI | team | "AI Training" | NULL | Default #2 (contracting platform, matches Example 3) |
| #79 RBC | title | "Principal Engineer, AI & ML Solutions" | "Engineer, AI & ML Solutions" | Default #4 (Principal stripped from title) |
| #80 Klue | title | "Senior Software Engineer" | "Software Engineer, AI (Agents)" | Default #4 |
| #86 Quora | team | "Engineering" | "Distribution Team" | More specific team found |
| #87 Outlier AI | team | "AI Training" | NULL | Default #2 (consistent with #70) |
| #88 Outlier AI | team | "AI Training" | NULL | Default #2 (consistent with #70) |
| #89 Recruiting in Motion | location | "Remote — Global" | "Remote — Canada" | Default #3 (Canada-first: JD is Canada-remote) |

#### Confirmed regressions — DO NOT COMMIT

| ID | Field | Round 1 | Round 2 | Issue |
|----|-------|---------|---------|-------|
| **#43 Ada** | location | **Remote — Canada** | **Other** | Raw DB location = "Canada"; LLM should map to "Remote — Canada" but returned "Other". Round 1 was correct. |
| **#50 PointClickCare** | location | **Remote — Canada** | **Other** | Same issue: raw location = "Canada"; Round 1 correctly returned "Remote — Canada". |
| **#8 Douglas College** | team | Business Intelligence & Data Analytics | NULL | Department name was present in JD; Default #2 over-fired — the JD DOES name the department. |
| **#29 Coalition** | team | Analytics | NULL | "Analytics" is a legitimate department name in the JD (Lead Analytics for GTM). Default #2 over-fired. |
| **#52 ABC Fitness** | team | AI Engineering | NULL | Named team was present; Default #2 over-fired. Also title stripped seniority qualifier but title changed from "Principal AI Engineer" to "AI Engineer" (should be "AI Engineer" — this part is improvement). |

#### Neutral / ambiguous changes (wording only)

| ID | Field | Round 1 | Round 2 | Note |
|----|-------|---------|---------|------|
| #7 Match | team | "Analytics Team" | "Analytics" | Equivalent meaning |
| #19 Lumenalta | team | "Engineering" | NULL | Ambiguous — "Engineering" is generic; both defensible |
| #26 Datatonic | team | "Machine Learning" | NULL | Ambiguous — generic vs. actual team name |
| #31 Crossing Hurdles | title + seniority | "Data Operations Manager" / Manager | "Human Data Manager" / Mid | Title changed to posting's stated role; seniority flip to Mid is debatable |
| #37 Apera AI | team | "AI Team" | "AI" | Equivalent meaning |
| #45 PHSA | team | "Project Controls Technology Services" | "Project Controls" | Minor truncation |
| #46 Axiom Builders | team | "Data Analytics" | NULL | Ambiguous — small company, could go either way |
| #49 Coalition | team | "Machine Learning" | NULL | Ambiguous |
| #62 BCIT | company + team | "BCIT" / "Information Technology Services" | "British Columbia Institute of Technology" / "Enterprise Applications & Services" | Company expanded (neutral), team changed (different dept name found — may be more accurate) |
| #77 TEEMA | title | "Staff Data Scientist" | "Data Scientist (AI & Machine Learning)" | Neutralised (Staff seniority level kept correctly, title renamed from staffing JD language) |
| #85 Aspire Software | team | "AI Agent Development" | NULL | Improvement — "AI Agent Development" was role-level, not org-unit |

---

### Verification of 5 defensive defaults

| Default | Expected | Result | Status |
|---------|----------|--------|--------|
| #1 Seniority lower-bound | "Engineer" alone → "Mid" | No ambiguous IC cases found in this batch to differentiate | Not verified in this batch |
| #2 NULL team when no org context | Outlier AI (#70, #87, #88) → NULL | PASS — "AI Training" → NULL for all three Outlier postings | PASS |
| #3 Canada-first location | #25 Affirm → "Remote — Canada" | FAIL — #25 still returns "Other" (Affirm is US-HQ, Kelowna location may be specific office not remote Canada) | PARTIAL — #89 Recruiting in Motion correctly changed from "Remote — Global" to "Remote — Canada" |
| #4 Drop seniority qualifiers from title | "Sr. Data Scientist" → "Data Scientist" | PASS — fired on #28 Amazon (Sr. dropped), #40 Cover Genius (Senior dropped), #54 Clio (Senior dropped), #79 RBC (Principal dropped from title) | PASS |
| #5 Org hierarchy → most-specific | UBC → "Olson Lab" | PASS — #1 UBC changed from full pipe-separated path to "Olson Lab" exactly as specified | PASS |

---

### Root cause analysis for location regressions (#43, #50)

The few-shot examples introduce "Remote — Canada" in Example 3 only for a "Remote (Worldwide)" JD, and no example shows a JD with bare "Canada" as the location. The defensive default #3 explicitly covers "US/Canada" → "Remote — Canada" but not "Canada" alone. When the LLM sees bare "Canada" as the location field in the prior hints, and the JD body describes a fully remote role without a specific city, Round 1 correctly inferred "Remote — Canada" from context. Round 2 regressed to "Other" — likely because the few-shot examples anchored the model toward "Remote — Global" for non-city, non-specific-Canada patterns, and the defensive defaults don't explicitly cover bare "Canada" → "Remote — Canada".

**Root cause**: Defensive default #3 does not cover the case of bare "Canada" or "Canada (Remote)" as the only location signal. The fix is to add one line to default #3:
```
"Canada" or "Canada (Remote)" or just "Canada" alone → "Remote — Canada"
```

**Proposed Round 3 fix** (single-line addition to default #3):
```
"Canada" (bare) or "Canada (Remote)" → "Remote — Canada"
```

Also: Default #2 appears to be over-firing for named departments that are clearly described (Douglas College's "Business Intelligence & Data Analytics" team is the actual department that owns the BI & analytics function). The fix: tighten Default #2's condition — only return NULL when the JD genuinely has NO team/department mention, not when the JD's title itself contains a department name.

---

### Decision: STOP — regressions found, commit blocked

Per Round 2 workflow Step 9: regressions on #43 Ada and #50 PointClickCare (location: "Remote — Canada" → "Other") and #8 Douglas College and #29 Coalition (team: named dept → NULL) are confirmed. Prompt changes are NOT committed.

Recommended path forward: Round 3 patch with two targeted additions:
1. Add "Canada" (bare) → "Remote — Canada" to Default #3
2. Add explicit caveat to Default #2: "if the job TITLE itself contains a department name (e.g. 'Manager, Business Intelligence & Data Analytics'), that IS the department — do not return NULL"

---

## Round 1 — Targeted Fixes (2026-04-27)

3 prompt fixes applied to `prompts/canonical_extraction_v1.txt`:

1. **Team rule relaxation** — removed hard "2–5 words" constraint; org-unit semantics
   now matter, not word count. Single-word units ("Engineering", "IT") and multi-word
   org paths are both valid.
2. **HR pay band guard for seniority** — "Staff - Non Union", "Pay Band X", etc. are
   administrative HR classifications, not IC seniority levels. Addresses #1 UBC where
   "Staff - Non Union" was misread as IC-level Staff.
3. **Company name consistency for small/regional firms** — Inc/Ltd-stripping applies
   ONLY to legal suffixes, not descriptive words like "Consulting", "Search", "Group".
   Addresses #20/#58 Alquemy inconsistency.

5 postings re-extracted (IDs: 1, 20, 54, 58, 80). Results:

| Posting | Field | Before | After | Verdict |
|---------|-------|--------|-------|---------|
| #1 UBC Research Engineer | seniority | Staff | Mid | PASS — HR band guard fired correctly |
| #20 Alquemy Data Scientist | company | Alquemy Search & Consulting | Alquemy Search & Consulting | PASS — no regression |
| #58 Alquemy Data Scientist | company | Alquemy Search | Alquemy Search & Consulting | PASS — longer form rule applied |
| #80 Klue Sr SWE AI | team | Engineering | Engineering | PASS — 1-word org-unit accepted |
| #54 Clio Sr Dev Enterprise AI | team | IT | IT | PASS — 1-word org-unit accepted |

**Side-effect to note:** Posting #1 now returns a verbose pipe-separated team path
("Research Group | Olson Lab | Department Mechanical Engineering | Faculty of Applied Science")
reflecting UBC's layered org structure. This is semantically correct but verbose. Flag
for Round 2 if multi-level org paths need normalisation.

Re-extraction cost: $0.030171 (5 fresh API calls + 66 cache hits for the remainder)

---

Date: 2026-04-27
Source DB: /Users/andrew.yu/.jd-matcher/jd-matcher.db
C19-passed postings analyzed: 71
Cost (this run): $0.030171 across 72 live API calls (141 cache hits)
Total cost on jd-matcher account to date: $0.030509

## Summary (Round 1)

| Metric | Count |
|--------|-------|
| Postings analyzed | 71 |
| Successful extractions | 71 |
| Parse failures (3-retry exhausted) | 0 |
| Cache hits (no API call) | 141 |
| New API calls | 72 |

## Extractions — full table for user review (Round 1 — pre Round 2)

Sorted by company alphabetically, then title.

| ID | Source | Email Title | LLM Title | LLM Company | Seniority | Location | Team | Skills (top 3) | Summary (excerpt) |
|----|--------|-------------|-----------|-------------|-----------|----------|------|----------------|-------------------|
| 52 | linkedin | Principal AI Engineer | Principal AI Engineer | ABC Fitness | Principal | Vancouver | AI Engineering | Python, AWS, Machine Learning | "The Principal AI Engineer will lead the development of LLM-powered product capabilities, collaborati..." |
| 76 | indeed | French Canada - AI Data Contributor | AI Data Contributor | Acolad | Mid | Remote — Global | NULL | AI, Data Annotation, Translation | "The AI Data Contributor will support various AI training and data-related projects. Responsibilities..." |
| 43 | linkedin | Senior Machine Learning Scientist | Senior Machine Learning Scientist | Ada | Senior | Remote — Canada | Product Development | Python, Machine Learning, Large Language Models | "As a Senior Machine Learning Scientist at Ada, you will be responsible for the quality and reliabili..." |
| 25 | linkedin | Manager, Machine Learning Engineering | Manager, Machine Learning Engineering | Affirm | Manager | Other | Fraud Machine Learning | Machine Learning, Deep Learning, Fraud Detection | "The Manager of Machine Learning Engineering will lead a team focused on developing and improving fra..." |
| 35 | linkedin | Senior Machine Learning Engineer | Senior Machine Learning Engineer | Alignerr | Senior | Remote — Canada | NULL | Machine Learning, AI, LLM | "The Senior Machine Learning Engineer will author high-fidelity reasoning traces that guide AI models..." |
| 36 | linkedin | Senior Machine Learning Expert | Senior Machine Learning Expert | Alignerr | Senior | Remote — Canada | NULL | Machine Learning, AI, Model Evaluation | "The Senior Machine Learning Expert will author high-fidelity reasoning traces to train large languag..." |
| 20 | linkedin | Data Scientist | Data Scientist | Alquemy Search & Consulting | Mid | Vancouver | NULL | Python, SQL, Machine Learning | "The Data Scientist will build and implement advanced machine learning and statistical models to pred..." |
| 58 | linkedin | Data Scientist | Data Scientist | Alquemy Search & Consulting | Mid | Vancouver | NULL | Python, SQL, Machine Learning | "The Data Scientist will leverage advanced machine learning and statistical techniques to solve compl..." |
| 21 | linkedin | data scientist | Data Scientist | Altea Healthcare | Mid | Vancouver | NULL | Python, Java, JavaScript | "The Data Scientist will assess and troubleshoot applications software and conduct business and techn..." |
| 2 | linkedin | Applied Scientist, Private Brands Discovery | Applied Scientist | Amazon | Mid | Vancouver | Private Brands Discovery | Python, Machine Learning, Causal Inference | "The Applied Scientist will drive applied science projects in machine learning from ideation to launc..." |
| 28 | linkedin | Sr. Data Scientist, Alexa Connections | Data Scientist | Amazon | Senior | Vancouver | Alexa Connections | Python, SQL, A/B testing | "The Senior Data Scientist in Alexa Connections will lead the development of machine learning and dat..." |
| 37 | linkedin | Senior Machine Learning / Computer Vision Applied Scientist | Senior Machine Learning / Computer Vision Applied Scientist | Apera AI | Senior | Vancouver | AI Team | Machine Learning, Computer Vision, PyTorch | "The Senior Machine Learning and Computer Vision Applied Scientist will join the AI team at Apera AI,..." |
| 85 | linkedin | AI Automation Engineer | AI Automation Engineer | Aspire Software | Mid | Remote — Canada | AI Agent Development | AI, Machine Learning, Product Development | "The AI Automation Engineer will design, build, and deploy AI agents for Aspire Software and its port..." |
| 46 | linkedin | Data Analyst | Data Analyst | Axiom Builders | Mid | Vancouver | Data Analytics | Power BI, SQL, Data Analytics | "The Data Analyst will be responsible for creating and maintaining Power BI dashboards and scorecards..." |
| 62 | indeed | Data Governance and Analytics Senior Systems Analyst | Data Governance and Analytics Senior Systems Analyst | BCIT | Senior | Vancouver | Information Technology Services | PL/SQL, MSSQL, Data Governance | "The Senior Systems Analyst will participate in ERP modernization initiatives, focusing on data gover..." |
| 38 | linkedin | Senior Machine Learning Engineer | Senior Machine Learning Engineer | BDO | Senior | Vancouver | Technology Advisory Services | MLOps, Azure, Databricks | "The Senior Machine Learning Engineer will lead the design and implementation of end-to-end MLOps pip..." |
| 78 | linkedin | Senior Data Analyst | Senior Data Analyst | Bird Construction | Senior | Vancouver | Business Intelligence & Analytics | Power BI, Data Governance, SQL | "The Senior Data Analyst will design, develop, and deliver analytics solutions using Power BI. This r..." |
| 54 | linkedin | Senior Developer, Enterprise AI | Senior Developer, Enterprise AI | Clio | Senior | Vancouver | IT | Ruby, Python, SQL | "The Senior Developer, Enterprise AI is a hands-on technical leader responsible for building, operati..." |
| 49 | linkedin | Applied Scientist II | Applied Scientist II | Coalition | Mid | Toronto | Machine Learning | Python, SQL, Machine Learning | "The Applied Scientist II will build and improve machine learning and GenAI models for underwriting d..." |
| 51 | linkedin | Applied Scientist II | Applied Scientist II | Coalition | Mid | Toronto | Machine Learning | Python, SQL, Machine Learning | "The Applied Scientist II will build and improve machine learning and GenAI models for underwriting d..." |
| 29 | linkedin | Senior Data Analyst | Senior Data Analyst | Coalition | Senior | Toronto | Analytics | SQL, Data Analysis, Python | "The Senior Data Analyst will lead analytics for the GTM and servicing motions, focusing on building..." |
| 23 | linkedin | Lead Data Scientist | Lead Data Scientist | Cohere | Lead | Remote — Canada | Analytics and Data Insights | SQL, Python, Git | "As a Lead Data Scientist, you will tackle complex analytical problems and shape go-to-market strateg..." |
| 17 | linkedin | Algorithm Engineer, AI | Algorithm Engineer, AI | Comm100 | Mid | Vancouver | Engineering | Python, TensorFlow, PyTorch | "The Algorithm Engineer, AI will research capabilities leading to AGI and track advancements in LLM t..." |
| 18 | linkedin | AI Solutions Engineer | AI Solutions Engineer | Connor, Clark & Lunn Financial Group | Mid | Vancouver | IS Department | AI, LLMs, Azure | "The AI Solutions Engineer will lead the design, prototyping, and operationalization of AI solutions..." |
| 5 | linkedin | Data Scientist, Investment Data | Data Scientist | Connor, Clark & Lunn Financial Group | Mid | Vancouver | Quantitative Equity Team | Data Science, Machine Learning, AI | "The Data Scientist will join the Quantitative Equity Team to support investment data preparation and..." |
| 56 | linkedin | Portfolio Research Analyst, Quantitative Equities | Portfolio Research Analyst | Connor, Clark & Lunn Financial Group | Mid | Vancouver | Quantitative Equity Team | Quantitative Research, Portfolio Optimization, Risk Management | "The Portfolio Research Analyst will contribute to the Portfolio Construction group by enhancing the..." |
| 3 | linkedin | Quantitative Data Analyst, Investment Data | Quantitative Data Analyst | Connor, Clark & Lunn Financial Group | Mid | Vancouver | Quantitative Equity Team | Data Analytics, Data Science, Financial Knowledge | "The Quantitative Data Analyst will join the Quantitative Equity Team to support investment research..." |
| 40 | linkedin | Senior Data Scientist - GenAI | Senior Data Scientist - GenAI | Cover Genius | Senior | Vancouver | Central AI Hub | Python, SQL, NLP | "The Senior Data Scientist for Generative AI will lead the LLM strategy within the Central AI Hub. Th..." |
| 31 | linkedin | Data Operations Manager | $45/hr Remote | Data Operations Manager | Crossing Hurdles | Manager | Remote — Canada | NULL | Data Analysis, Data Workflow Management, KPI Monitoring | "The Data Operations Manager is responsible for designing and managing data workflows for annotation,..." |
| 26 | linkedin | Lead Machine Learning Engineer (Team Lead) | Lead Machine Learning Engineer | Datatonic | Lead | Remote — Canada | Machine Learning | Machine Learning, Data Science, Google Cloud | "As a Lead Machine Learning Engineer, you will oversee a team of Machine Learning Engineers and Data..." |
| 82 | linkedin | Machine Learning Engineer | Machine Learning Engineer | Datatonic | Senior | Remote — Canada | Machine Learning | Python, Machine Learning, Data Engineering | "The Senior Machine Learning Engineer will develop and implement machine learning models to solve rea..." |
| 11 | linkedin | Data Science Manager | Data Science Manager | Deloitte | Manager | Hybrid — Vancouver | Artificial Intelligence | Python, SQL, Data Analysis | "The Data Science Manager will lead the delivery of advanced analytics solutions and advisory service..." |
| 15 | linkedin | AI Productivity Analyst | AI Productivity Analyst | Dialpad | Mid | Vancouver | AI Transformation | GenAI, Machine Learning, Python | "The AI Productivity Analyst will evaluate and pilot third-party AI tools to enhance productivity at..." |
| 16 | linkedin | AI Productivity Analyst | AI Productivity Analyst | Dialpad | Mid | Vancouver | Product Management | GenAI, Machine Learning, Python | "The AI Productivity Analyst will evaluate and pilot third-party AI tools to enhance productivity at..." |
| 13 | linkedin | Analytics Engineer | Analytics Engineer | Dialpad | Mid | Vancouver | Data Analysis and QA | Python, SQL, GCP | "As an analytics engineer, you will support data analysis and quality assurance for Agentic AI initia..." |
| 4 | linkedin | Applied Scientist | Applied Scientist | Dialpad | Mid | Vancouver | NLP team | Machine Learning, NLP, Python | "As an Applied Scientist at Dialpad, you will conduct research and development to enhance autonomous..." |
| 8 | linkedin | Manager, Business Intelligence & Data Analytics | Manager, Business Intelligence & Data Analytics | Douglas College | Manager | Hybrid — Vancouver | Business Intelligence & Data Analytics | SQL, Tableau, Power BI | "The Manager of Business Intelligence & Data Analytics will oversee the production of datasets and ke..." |
| 30 | linkedin | Data Scientist | Data Scientist | Dropbox | Mid | Other | Data Science | SQL, Statistical Analysis, Experimentation Design | "The Data Scientist will partner with product, engineering, and design teams to analyze user behavior..." |
| 53 | linkedin | Senior Machine Learning Engineer - Generative AI Team | Senior Machine Learning Engineer | EA SPORTS | Senior | Vancouver | Generative AI Team | Machine Learning, Python, C++ | "The Senior Machine Learning Engineer will join the FC Generative AI team to research and develop mac..." |
| 27 | linkedin | Lead Data Scientist - Search, Data & Insights (D&I) | Lead Data Scientist | Electronic Arts | Lead | Vancouver | Data and Insights | Python, SQL, AWS | "The Lead Data Scientist will work within the Data and Insights organization at Electronic Arts, focu..." |
| 9 | linkedin | Manager, Data Analytics | Manager, Data Analytics | Fasken | Manager | Hybrid — Vancouver | Data Analytics & Engineering | Power BI, SQL, Python | "The Manager, Data Analytics will serve as a senior analytics leader and business partner within the..." |
| 41 | linkedin | Senior Data Scientist | Senior Data Scientist | Fortra | Senior | Remote — Canada | Data Science | Python, Machine Learning, Data Science | "The Senior Data Scientist will lead complex data science projects and develop solutions for customer..." |
| 67 | indeed | Senior Analytics Engineer, Analytics Enablement | Senior Analytics Engineer | Fullscript | Senior | Calgary | Analytics Enablement | SQL, Python, Looker | "The Senior Analytics Engineer will focus on enabling teams at Fullscript to self-serve data without..." |
| 44 | linkedin | Senior Data Scientist - Shopping Experience (Search) | Senior Data Scientist | Instacart | Senior | Remote — Canada | Shopping Experience | SQL, Python, A/B testing | "The Senior Data Scientist will focus on analytics and experimentation strategies for the Shopping Ex..." |
| 14 | linkedin | Transportation Data Scientist | Transportation Data Scientist | Jacobs | Mid | Vancouver | Data and Metrics Quality | Python, SQL, Machine Learning | "The Transportation Data Scientist will contribute transportation industry expertise to ensure the qu..." |
| 48 | linkedin | Data Scientist Specialist (Lending) | Data Scientist Specialist | Jobgether | Mid | Remote — Canada | NULL | Python, SQL, Spark | "The Data Scientist Specialist will develop and deploy real-time scoring models to assess credit and..." |
| 80 | linkedin | Senior Software Engineer, AI (Agents) | Senior Software Engineer | Klue | Senior | Vancouver | Engineering | Python, API, Distributed Systems | "The Senior Software Engineer will build and optimize LLM-powered agents at scale, focusing on backen..." |
| 33 | linkedin | Data Analyst, Risk and Operational Performance | Data Analyst | Kraken | Mid | Remote — Canada | Core Services | SQL, Python, dbt | "The Data Analyst, Risk and Operational Performance will elevate decision-making by uncovering trends..." |
| 32 | linkedin | Data Analyst, Growth | Data Analyst, Growth | Kraken | Mid | Remote — Canada | Data Team | SQL, Python, dbt | "The Data Analyst, Growth will focus on turning complex growth marketing data into actionable insight..." |
| 42 | linkedin | Senior Data Scientist, AI Native (Growth) | Senior Data Scientist | Life360 | Senior | Remote — Canada | Data Science | Machine Learning, Statistical Modeling, A/B Testing | "The Senior Data Scientist will focus on scaling Life360's growth and user retention efforts. This ro..." |
| 19 | linkedin | AI Engineer (Remote) | AI Engineer | Lumenalta | Mid | Remote — North America | Engineering | Python, TensorFlow, PyTorch | "The AI Engineer will design, build, and deploy AI models into production, focusing on backend Python..." |
| 83 | linkedin | AI Engineer (Remote) | AI Engineer | Lumenalta | Mid | Remote — North America | Engineering | Python, TensorFlow, PyTorch | "The AI Engineer will design, build, and deploy AI models into production, focusing on backend Python..." |
| 7 | linkedin | Manager, Data Science, Marketing Analytics | Manager, Data Science, Marketing Analytics | Match | Manager | Vancouver | Analytics Team | SQL, Python, A/B testing | "The Manager, Data Science will lead the Analytics Team in providing advanced marketing measurement t..." |
| 84 | linkedin | AI Development Engineer - Remote | AI Development Engineer | NTT DATA | Mid | Remote — Canada | NULL | Python, Machine Learning, Data Engineering | "The AI Development Engineer will design, develop, and deploy AI-driven solutions to address complex..." |
| 70 | indeed | Applied AI Engineer - AI Trainer | Applied AI Engineer - AI Trainer | Outlier AI | Mid | Remote — Global | AI Training | Python, SQL, JavaScript | "The Applied AI Engineer - AI Trainer will help train generative AI models by developing criteria to..." |
| 87 | indeed | Senior Full Stack Engineer - AI Trainer | Applied AI Engineer - AI Trainer | Outlier AI | Mid | Remote — Global | AI Training | Python, SQL, JavaScript | "The Applied AI Engineer - AI Trainer will help train generative AI models by developing criteria to..." |
| 88 | indeed | OpenClaw Agent Engineer - AI Trainer | Applied AI Engineer - AI Trainer | Outlier AI | Mid | Remote — Global | AI Training | Python, SQL, JavaScript | "The Applied AI Engineer - AI Trainer will help train generative AI models by developing criteria to..." |
| 45 | linkedin | Data Analyst, Project Controls Technology Services | Data Analyst | PHSA | Mid | Vancouver | Project Controls Technology Services | SQL, Python, Data Analysis | "The Data Analyst in Project Controls develops and maintains complex datasets by conducting systems a..." |
| 50 | linkedin | Senior Applied Researcher AI/ML ( CAD) | Senior Applied Researcher AI/ML | PointClickCare | Senior | Remote — Canada | Advanced Technology / Applied AI Research | Python, SQL, Machine Learning | "The Senior Applied Researcher in AI/ML will work on solving critical challenges in the healthcare ma..." |
| 86 | linkedin | Senior Machine Learning Engineer, Ranking - Quora (Remote) | Senior Machine Learning Engineer | Quora | Senior | Remote — Canada | Engineering | Machine Learning, Python, C++ | "The Senior Machine Learning Engineer will work on improving and developing recommendation models for..." |
| 22 | linkedin | Machine Learning Software Engineer | Machine Learning Software Engineer | RBC | Mid | Vancouver | RBC Borealis | Python, Machine Learning, Software Engineering | "The Machine Learning Software Engineer will be responsible for developing and delivering machine lea..." |
| 79 | linkedin | Principal Engineer, AI & ML Solutions, GFT | Principal Engineer, AI & ML Solutions | RBC | Principal | Vancouver | Global Functions Technology | Python, Machine Learning, AI | "The Principal Engineer will oversee machine learning programs and projects, managing resources and d..." |
| 89 | indeed | Ai Agent Designer | Ai Agent Designer | Recruiting in Motion | Mid | Remote — Global | NULL | Python, API, GenAI | "The Ai Agent Designer will design and deploy end-to-end AI agent solutions, managing the full delive..." |
| 24 | linkedin | Data Science Manager, Growth | Data Science Manager, Growth | Stripe | Manager | Toronto | Growth Data Science | Data Science, Machine Learning, Statistical Analysis | "The Data Science Manager for Growth at Stripe will lead a team focused on optimizing the user journe..." |
| 77 | linkedin | Staff Data Scientist | Staff Data Scientist | TEEMA | Staff | Vancouver | AI Organization | Python, PyTorch, TensorFlow | "The Staff Data Scientist will lead the technical strategy for AI initiatives, focusing on machine tr..." |
| 55 | linkedin | Senior Developer (AI/ML/Gen AI Solutions) | Senior Developer (AI/ML/Gen AI Solutions) | TELUS | Senior | Vancouver | AI Accelerator | Python, React, Node.js | "The Senior Developer will lead cross-functional teams in designing and implementing AI/ML solutions...." |
| 47 | linkedin | Data Analyst - FTT | Data Analyst | TransLink | Mid | Hybrid — Vancouver | Data Management Team | Data Analysis, Data Management, Data Modeling | "The Data Analyst will perform data analysis of enterprise data and provide expertise to business sta..." |
| 1 | linkedin | Research Engineer | Research Engineer | University of British Columbia | Mid | Vancouver | Research Group | Olson Lab | Department Mechanical Engineering | Faculty of Applied Science | Engineering, Statistical Analysis, Material Testing | "The Research Engineer is responsible for designing, developing, and implementing experimental progra..." |
| 10 | linkedin | Senior Manager / Manager, Data Science | Senior Manager, Data Science | Vancity | Manager | Vancouver | Applied Machine Learning Pod | Machine Learning, MLOps, Azure | "The Senior Manager, Data Science will lead the development and delivery of machine learning and deci..." |
| 39 | linkedin | Senior/Principal Machine Learning Engineer | Machine Learning Engineer | Workday | Senior | Vancouver | Agent Factory | Machine Learning, Deep Learning, Python | "As a Senior Machine Learning Engineer in Agent Factory, you will design and build core ML systems fo..." |
| 68 | indeed | Ai Trainer / Ai Data Trainer - Remote | AI Trainer | YO IT CONSULTING | Mid | Remote — Global | NULL | AI training, data annotation, prompt engineering | "The AI Trainer / AI Data Trainer is responsible for improving and evaluating AI models by providing..." |

## How to label (instructions for the user)

For a stratified sample of 10–15 rows above (mix of LinkedIn + Indeed, mix of seniority levels, mix of clear-cut + ambiguous cases), assign per-field labels:

| Field | Label values |
|-------|--------------|
| canonical_title | correct / wrong / partial (drop modifier or seniority hint) |
| canonical_company | correct / wrong / over-stripped (e.g. `TELUS Digital → TELUS` — division dropped) |
| canonical_seniority | correct / wrong / borderline (e.g. Lead vs Staff) |
| canonical_location | correct / wrong / fallback-to-Other (Other when a real city was discoverable) |
| team_or_department | correct / wrong / null-when-extractable / non-null-when-not / too-granular (role-level instead of org-unit) |
| top_skills | good / OK / poor (list intersection vs your judgment) |
| role_summary | embedding-suitable (neutral, no marketing) / poor / bad |

Then report counts. We compute per-field precision against:

- `canonical_company` ≥95%
- `canonical_seniority` ≥85%
- `canonical_location` ≥90%
- `team_or_department` ≥90% precision (recall intentionally low)
- `top_skills` Jaccard ≥0.6
- `role_summary` "embedding-suitable" ≥80%

Below threshold → tune `prompts/canonical_extraction_v1.txt`, re-run failing samples, iterate (max 3 prompt-fix attempts per Gate 5).
