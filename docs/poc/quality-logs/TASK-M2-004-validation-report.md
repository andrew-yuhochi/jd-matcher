# TASK-M2-004 — Filter Validation Report (Iteration 1)

Date: 2026-04-27
Source DB: /Users/andrew.yu/.jd-matcher/jd-matcher.db
Total postings analyzed: 91  (skipped 0 with empty canonical_title)
Config snapshot: config/title_filters.yaml @ commit 096dbb6

## Summary

| Metric            | Count | % of analyzed |
|-------------------|-------|---------------|
| Total analyzed    | 91   | 100%          |
| Filtered (drop)   | 9   | 9.9%       |
| Passed (pass)     | 82   | 90.1%       |

## Filtered postings — for user review (label correct-drop or FALSE POSITIVE)

| ID | Source | Title | Company | Location | Matched Pattern |
|----|--------|-------|---------|----------|-----------------|
| 12 | linkedin_email,linkedin_hydrator | Clinical Business Intelligence Manager | Alignerr | Vancouver, British Columbia, Canada | `\bBusiness Intelligence (Analyst|Developer|Specialist|Manager|Engineer)\b` |
| 57 | linkedin_email,linkedin_hydrator | Associate Director, Asset Modelling - STG Life Solutions | Aon | Vancouver, British Columbia, Canada | `\bDirector\b` |
| 63 | indeed_email,indeed_hydrator | Senior QA Analyst - Platform Data Integration | Servus Credit Union | Calgary | `\bQA (Engineer|Analyst|Tester|Specialist)\b` |
| 64 | indeed_email,indeed_hydrator | Software Engineer, iOS Core Product - Waterloo, Canada | Speechify | Waterloo | `\bSoftware (Engineer|Developer)\b` |
| 65 | indeed_email,indeed_hydrator | Software Engineer, iOS Core Product - Montreal, Canada | Speechify | Montréal | `\bSoftware (Engineer|Developer)\b` |
| 69 | indeed_email,indeed_hydrator | Software Engineer | MORPH LABS | Remote | `\bSoftware (Engineer|Developer)\b` |
| 71 | indeed_email,indeed_hydrator | Software Engineer, iOS Core Product - Vancouver, Canada | Speechify | Vancouver | `\bSoftware (Engineer|Developer)\b` |
| 81 | indeed_email,indeed_hydrator | Senior Full-Stack Engineer | CyberCoders |  | `\bFull.?Stack (Engineer|Developer)\b` |
| 85 | linkedin_email,linkedin_hydrator | AI Automation Engineer | Aspire Software | Canada | `\bAutomation (Engineer|Developer|Tester)\b` |

## Passed postings — for user spot-check (label correct-pass or FALSE NEGATIVE)

Sorted by title alphabetically for scanning.

| ID | Source | Title | Company | Location |
|----|--------|-------|---------|----------|
| 89 | indeed_email,indeed_hydrator | Ai Agent Designer | Recruiting in Motion | York |
| 84 | linkedin_email,linkedin_hydrator | AI Development Engineer - Remote | NTT DATA North America | Toronto, Ontario, Canada |
| 19 | linkedin_email,linkedin_hydrator | AI Engineer (Remote) | Lumenalta | Vancouver, British Columbia, Canada |
| 83 | linkedin_email,linkedin_hydrator | AI Engineer (Remote) | Lumenalta | Canada |
| 60 | linkedin_email,linkedin_hydrator | AI Intern | ProCogia | Vancouver, British Columbia, Canada |
| 15 | linkedin_email,linkedin_hydrator | AI Productivity Analyst | Dialpad | Vancouver, British Columbia, Canada |
| 16 | linkedin_email,linkedin_hydrator | AI Productivity Analyst | Dialpad Japan | Vancouver, British Columbia, Canada |
| 18 | linkedin_email,linkedin_hydrator | AI Solutions Engineer | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 66 | indeed_email,indeed_hydrator | AI Summer Intern | Triangulam Labs |  |
| 68 | indeed_email,indeed_hydrator | Ai Trainer / Ai Data Trainer - Remote | YO IT CONSULTING | Remote |
| 17 | linkedin_email,linkedin_hydrator | Algorithm Engineer, AI | Comm100 | Vancouver, British Columbia, Canada |
| 13 | linkedin_email,linkedin_hydrator | Analytics Engineer | Dialpad | Vancouver, British Columbia, Canada |
| 70 | indeed_email,indeed_hydrator | Applied AI Engineer - AI Trainer | Outlier Ai |  |
| 4 | linkedin_email,linkedin_hydrator | Applied Scientist | Dialpad | Vancouver, British Columbia, Canada |
| 49 | linkedin_email,linkedin_hydrator | Applied Scientist II | Coalition, Inc. | Toronto, Ontario, Canada |
| 51 | linkedin_email,linkedin_hydrator | Applied Scientist II | Coalition, Inc. | Canada |
| 2 | linkedin_email,linkedin_hydrator | Applied Scientist, Private Brands Discovery | Amazon | Vancouver, British Columbia, Canada |
| 75 | indeed_email,indeed_hydrator | Clinical Research Assistant | University of British Columbia | Vancouver |
| 46 | linkedin_email,linkedin_hydrator | Data Analyst | Axiom Builders | Vancouver, British Columbia, Canada |
| 47 | linkedin_email,linkedin_hydrator | Data Analyst - FTT | TransLink | Vancouver, British Columbia, Canada |
| 32 | linkedin_email,linkedin_hydrator | Data Analyst, Growth | Kraken | Canada |
| 45 | linkedin_email,linkedin_hydrator | Data Analyst, Project Controls Technology Services | Provincial Health Services Authority | Burnaby, British Columbia, Canada |
| 33 | linkedin_email,linkedin_hydrator | Data Analyst, Risk and Operational Performance | Kraken | Canada |
| 62 | indeed_email,indeed_hydrator | Data Governance and Analytics Senior Systems Analyst | British Columbia Institute of Technology (BCIT) | Burnaby |
| 31 | linkedin_email,linkedin_hydrator | Data Operations Manager | $45/hr Remote | Crossing Hurdles | Canada |
| 11 | linkedin_email,linkedin_hydrator | Data Science Manager | Deloitte | Vancouver, British Columbia, Canada |
| 24 | linkedin_email,linkedin_hydrator | Data Science Manager, Growth | Stripe | Toronto, Ontario, Canada |
| 20 | linkedin_email,linkedin_hydrator | Data Scientist | Alquemy Search & Consulting | Vancouver, British Columbia, Canada |
| 21 | linkedin_email,linkedin_hydrator | data scientist | Altea Healthcare | Burnaby, British Columbia, Canada |
| 30 | linkedin_email,linkedin_hydrator | Data Scientist | Dropbox | Canada |
| 58 | linkedin_email,linkedin_hydrator | Data Scientist | Alquemy Search & Consulting | Vancouver, British Columbia, Canada |
| 48 | linkedin_email,linkedin_hydrator | Data Scientist Specialist (Lending) | Jobgether | Canada |
| 5 | linkedin_email,linkedin_hydrator | Data Scientist, Investment Data | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 90 | indeed_email,indeed_hydrator | Director, Senior AI Engineer - Ontario, Canada (Remote) | IKS Health | Remote |
| 72 | indeed_email,indeed_hydrator | Flutter Developer | Abomis Innovations | Vancouver |
| 76 | indeed_email,indeed_hydrator | French Canada - AI Data Contributor | Acolad | Remote |
| 34 | linkedin_email,linkedin_hydrator | Fresher Data Analyst | Joveo AI | Canada |
| 73 | indeed_email,indeed_hydrator | Junior Environmental Scientist or EIT | Stantec | Burnaby |
| 23 | linkedin_email,linkedin_hydrator | Lead Data Scientist | Cohere | Canada |
| 27 | linkedin_email,linkedin_hydrator | Lead Data Scientist - Search, Data & Insights (D&I) | Electronic Arts (EA) | Vancouver, British Columbia, Canada |
| 26 | linkedin_email,linkedin_hydrator | Lead Machine Learning Engineer (Team Lead) | Datatonic | Canada |
| 82 | linkedin_email,linkedin_hydrator | Machine Learning Engineer | Datatonic | Canada |
| 22 | linkedin_email,linkedin_hydrator | Machine Learning Software Engineer | RBC | Vancouver, British Columbia, Canada |
| 8 | linkedin_email,linkedin_hydrator | Manager, Business Intelligence & Data Analytics | Douglas College | New Westminster, British Columbia, Canada |
| 9 | linkedin_email,linkedin_hydrator | Manager, Data Analytics | Fasken | Vancouver, British Columbia, Canada |
| 7 | linkedin_email,linkedin_hydrator | Manager, Data Science, Marketing Analytics | Match | Vancouver, British Columbia, Canada |
| 25 | linkedin_email,linkedin_hydrator | Manager, Machine Learning Engineering | Affirm | Kelowna, British Columbia, Canada |
| 88 | indeed_email,indeed_hydrator | OpenClaw Agent Engineer - AI Trainer | Outlier Ai |  |
| 91 | indeed_email,indeed_hydrator | Personalized Internet Assessor - Persian speakers in Canada | TELUS Digital | Remote |
| 56 | linkedin_email,linkedin_hydrator | Portfolio Research Analyst, Quantitative Equities | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 52 | linkedin_email,linkedin_hydrator | Principal AI Engineer | ABC Fitness | Vancouver, British Columbia, Canada |
| 79 | linkedin_email,linkedin_hydrator | Principal Engineer, AI & ML Solutions, GFT | RBC | Vancouver, British Columbia, Canada |
| 3 | linkedin_email,linkedin_hydrator | Quantitative Data Analyst, Investment Data | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 6 | linkedin_email,linkedin_hydrator | Research Associate | The University of British Columbia | Vancouver, British Columbia, Canada |
| 1 | linkedin_email,linkedin_hydrator | Research Engineer | The University of British Columbia | Vancouver, British Columbia, Canada |
| 67 | indeed_email,indeed_hydrator | Senior Analytics Engineer, Analytics Enablement | Fullscript | Calgary |
| 50 | linkedin_email,linkedin_hydrator | Senior Applied Researcher AI/ML ( CAD) | PointClickCare | Canada |
| 29 | linkedin_email,linkedin_hydrator | Senior Data Analyst | Coalition, Inc. | Toronto, Ontario, Canada |
| 78 | linkedin_email,linkedin_hydrator | Senior Data Analyst | Bird Construction | Richmond, British Columbia, Canada |
| 41 | linkedin_email,linkedin_hydrator | Senior Data Scientist | Fortra | Canada |
| 40 | linkedin_email,linkedin_hydrator | Senior Data Scientist - GenAI | Cover Genius | Vancouver, British Columbia, Canada |
| 44 | linkedin_email,linkedin_hydrator | Senior Data Scientist - Shopping Experience (Search) | Instacart | Canada |
| 42 | linkedin_email,linkedin_hydrator | Senior Data Scientist, AI Native (Growth) | Life360 | Canada |
| 55 | linkedin_email,linkedin_hydrator | Senior Developer (AI/ML/Gen AI Solutions) | TELUS | Burnaby, British Columbia, Canada |
| 54 | linkedin_email,linkedin_hydrator | Senior Developer, Enterprise AI | Clio | Vancouver, British Columbia, Canada |
| 87 | indeed_email,indeed_hydrator | Senior Full Stack Engineer - AI Trainer | Outlier Ai |  |
| 37 | linkedin_email,linkedin_hydrator | Senior Machine Learning / Computer Vision Applied Scientist | Apera AI | Vancouver, British Columbia, Canada |
| 35 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer | Alignerr | Vancouver, British Columbia, Canada |
| 38 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer | BDO Canada | Vancouver, British Columbia, Canada |
| 53 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer - Generative AI Team | EA SPORTS | Vancouver, British Columbia, Canada |
| 86 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer, Ranking - Quora (Remote) | Quora | Canada |
| 36 | linkedin_email,linkedin_hydrator | Senior Machine Learning Expert | Alignerr | Vancouver, British Columbia, Canada |
| 43 | linkedin_email,linkedin_hydrator | Senior Machine Learning Scientist | ada CX | Canada |
| 10 | linkedin_email,linkedin_hydrator | Senior Manager / Manager, Data Science | Vancity | Vancouver, British Columbia, Canada |
| 61 | linkedin_email,linkedin_hydrator | Senior Manager, Trial Operations | Xenon Pharmaceuticals Inc. | Vancouver, British Columbia, Canada |
| 80 | linkedin_email,linkedin_hydrator | Senior Software Engineer, AI (Agents) | Klue | Vancouver, British Columbia, Canada |
| 59 | linkedin_email,linkedin_hydrator | Senior, Economic Advisory (Vancouver) | EY | Vancouver, British Columbia, Canada |
| 39 | linkedin_email,linkedin_hydrator | Senior/Principal Machine Learning Engineer | Workday | Vancouver, British Columbia, Canada |
| 28 | linkedin_email,linkedin_hydrator | Sr. Data Scientist, Alexa Connections | Amazon | Vancouver, British Columbia, Canada |
| 77 | linkedin_email,linkedin_hydrator | Staff Data Scientist | TEEMA | Vancouver, British Columbia, Canada |
| 14 | linkedin_email,linkedin_hydrator | Transportation Data Scientist | Jacobs | Burnaby, British Columbia, Canada |
| 74 | indeed_email,indeed_hydrator | Water Resources Engineer/Scientist/Modeller | AECOM | Burnaby |

## How to label (instructions for the user)

For each row above, mentally tag:
- **Filtered**: correct-drop  /  FALSE POSITIVE (legit job we lost)
- **Passed**:   correct-pass  /  FALSE NEGATIVE (irrelevant job that slipped through)

Then we tune `config/title_filters.yaml`:
- False positives → add allow override pattern, OR narrow the deny pattern
- False negatives → add new deny pattern

Re-run `.venv/bin/python -m jd_matcher.filter.validate` after each YAML edit. Iterate until:
- Precision >= 95%  (filtered \ false_positives) / filtered  >= 0.95
- Recall >= 98%      (passed \ false_negatives) / total_legit >= 0.98
