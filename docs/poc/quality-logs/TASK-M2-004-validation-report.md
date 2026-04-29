# TASK-M2-004 — Filter Validation Report (Iteration 1)

Date: 2026-04-28
Source DB: /Users/andrew.yu/.jd-matcher/jd-matcher.db
Total postings analyzed: 183  (skipped 0 with empty canonical_title)
Config snapshot: config/title_filters.yaml @ commit eff5063

## Summary

| Metric            | Count | % of analyzed |
|-------------------|-------|---------------|
| Total analyzed    | 183   | 100%          |
| Filtered (drop)   | 15   | 8.2%       |
| Passed (pass)     | 168   | 91.8%       |

## Filtered postings — for user review (label correct-drop or FALSE POSITIVE)

| ID | Source | Title | Company | Location | Matched Pattern |
|----|--------|-------|---------|----------|-----------------|
| 29 | linkedin_email,linkedin_hydrator | Finance & Strategy Manager, Hopper/ HTS (100% Remote - Canada) | Hopper | Vancouver, British Columbia, Canada | `(?i)\bFinance.{0,5}(&|and)\s*Strategy\b` |
| 32 | linkedin_email,linkedin_hydrator | Scientist II, Analytical Development | Cytiva | Vancouver, British Columbia, Canada | `(?i)\bAnalytical Development\b` |
| 34 | linkedin_email,linkedin_hydrator | R&D Scientist, Novel Ingredients | Marine Biologics | Vancouver, British Columbia, Canada | `(?i)\bNovel Ingredients\b` |
| 36 | linkedin_email,linkedin_hydrator | Data Scientist, Early Career (Canada) | Jobright.ai | Canada | `(?i)\bEarly Career\b` |
| 37 | linkedin_email,linkedin_hydrator | Machine Learning Engineer - Early Career (Canada) | Jobright.ai | Canada | `(?i)\bEarly Career\b` |
| 47 | linkedin_email,linkedin_hydrator | Process Development Scientist, GMP Media | STEMCELL Technologies | Burnaby, British Columbia, Canada | `(?i)\bGMP\s+Media\b` |
| 99 | linkedin_email,linkedin_hydrator | Data Scientist, Early Career (Canada) | Jobright.ai | Canada | `(?i)\bEarly Career\b` |
| 103 | linkedin_email,linkedin_hydrator | Machine Learning Engineer - Early Career (Canada) | Jobright.ai | Canada | `(?i)\bEarly Career\b` |
| 109 | linkedin_email,linkedin_hydrator | Partner Alliance Analyst | 1Password | Canada | `(?i)\bPartner Alliance\b` |
| 163 | indeed_email,indeed_hydrator | Startup Event Representative (Tech / Web Summit Vancouver) |  |  | `(?i)\bEvent Representative\b` |
| 171 | indeed_email,indeed_hydrator | AI Trainer - Freelance Data Annotator |  |  | `(?i)\b(AI Trainer|AI Data Trainer|Data Annotator|Data Contributor)\b` |
| 172 | indeed_email,indeed_hydrator | Email Operations Specialist (Klaviyo/AI/Figma/Claude) |  |  | `(?i)\bEmail Operations\b` |
| 179 | indeed_email,indeed_hydrator | Creative Lead, Growth & Storytelling |  |  | `(?i)\bCreative Lead\b` |
| 182 | indeed_email,indeed_hydrator | Ai Trainer / Ai Data Trainer - Remote |  |  | `(?i)\b(AI Trainer|AI Data Trainer|Data Annotator|Data Contributor)\b` |
| 183 | indeed_email,indeed_hydrator | French Canada - AI Data Contributor |  |  | `(?i)\b(AI Trainer|AI Data Trainer|Data Annotator|Data Contributor)\b` |

## Passed postings — for user spot-check (label correct-pass or FALSE NEGATIVE)

Sorted by title alphabetically for scanning.

| ID | Source | Title | Company | Location |
|----|--------|-------|---------|----------|
| 54 | linkedin_email,linkedin_hydrator | Agentic AI Engineer | Joveo Ai | Canada |
| 124 | linkedin_email,linkedin_hydrator | AI / ML Engineer | Remote | Crossing Hurdles | Canada |
| 130 | linkedin_email,linkedin_hydrator | AI Automation Engineer | Aspire Software | Canada |
| 129 | linkedin_email,linkedin_hydrator | AI Development Engineer - Remote | NTT DATA North America | Toronto, Ontario, Canada |
| 63 | linkedin_email,linkedin_hydrator | AI Enablement Engineer | Electronic Arts (EA) | Vancouver, British Columbia, Canada |
| 2 | linkedin_email,linkedin_hydrator | AI Engineer (Remote) | Lumenalta | Canada |
| 4 | linkedin_email,linkedin_hydrator | AI Engineer (Remote) | Lumenalta | Vancouver, British Columbia, Canada |
| 52 | linkedin_email,linkedin_hydrator | AI Engineer (Remote) | Jobs Ai | Canada |
| 5 | linkedin_email,linkedin_hydrator | AI ML Engineer | Galent | Canada |
| 92 | linkedin_email,linkedin_hydrator | AI Productivity Analyst | Dialpad | Vancouver, British Columbia, Canada |
| 128 | linkedin_email,linkedin_hydrator | AI Productivity Analyst | Dialpad Japan | Vancouver, British Columbia, Canada |
| 165 | indeed_email,indeed_hydrator | AI Senior Machine Learning Engineer, General AI, ML & Big Data |  |  |
| 74 | linkedin_email,linkedin_hydrator | AI Sim - Staff ML Research Engineer | SandboxAQ | Canada |
| 23 | linkedin_email,linkedin_hydrator | AI Software Developer (Healthcare Systems & Automation) | Vancouver Psychology Centre | Vancouver, British Columbia, Canada |
| 90 | linkedin_email,linkedin_hydrator | AI Solution Architect | Diligent | Vancouver, British Columbia, Canada |
| 20 | linkedin_email,linkedin_hydrator | AI Solutions Engineer | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 57 | linkedin_email,linkedin_hydrator | AI Specialist - Applied ML Research | Xanadu | Toronto, Ontario, Canada |
| 53 | linkedin_email,linkedin_hydrator | AI/ML ENGINEER | AMworkplace | Canada |
| 108 | linkedin_email,linkedin_hydrator | AI/ML Engineer (ChatGPT, Claude, LLM, AgenticAI) | Diligente Technologies | Canada |
| 3 | linkedin_email,linkedin_hydrator | AI/ML Engineer - Remote | YO HR Consultancy | Canada |
| 24 | linkedin_email,linkedin_hydrator | Algorithm Engineer, AI | Comm100 | Vancouver, British Columbia, Canada |
| 22 | linkedin_email,linkedin_hydrator | Analytics Engineer | Dialpad | Vancouver, British Columbia, Canada |
| 64 | linkedin_email,linkedin_hydrator | Applied Scientist | Dialpad | Vancouver, British Columbia, Canada |
| 9 | linkedin_email,linkedin_hydrator | Applied Scientist II | Coalition, Inc. | Toronto, Ontario, Canada |
| 10 | linkedin_email,linkedin_hydrator | Applied Scientist II | Coalition, Inc. | Canada |
| 101 | linkedin_email,linkedin_hydrator | Applied Scientist, Customer Growth | Thumbtack | Ontario, Canada |
| 88 | linkedin_email,linkedin_hydrator | Applied Scientist, Private Brands Discovery | Amazon | Vancouver, British Columbia, Canada |
| 6 | linkedin_email,linkedin_hydrator | Artificial Intelligence Engineer | Galent | Canada |
| 152 | linkedin_email,linkedin_hydrator | Associate AI Evaluation Scientist | BMO | Vancouver, British Columbia, Canada |
| 126 | linkedin_email,linkedin_hydrator | Associate Data Scientist - User Fraud | Spotify | Toronto, Ontario, Canada |
| 50 | linkedin_email,linkedin_hydrator | Bioinformatics Scientist (Remote) | Jobs Ai | Canada |
| 25 | linkedin_email,linkedin_hydrator | Data Analyst | ADF Medical | Vancouver, British Columbia, Canada |
| 146 | linkedin_email,linkedin_hydrator | Data Analyst | Axiom Builders | Vancouver, British Columbia, Canada |
| 59 | linkedin_email,linkedin_hydrator | Data Analyst (Remote) | Jobs Ai | Canada |
| 147 | linkedin_email,linkedin_hydrator | Data Analyst - FTT | TransLink | Vancouver, British Columbia, Canada |
| 60 | linkedin_email,linkedin_hydrator | Data Analyst | $80/hr Remote | Crossing Hurdles | Canada |
| 141 | linkedin_email,linkedin_hydrator | Data Analyst, Growth | Kraken | Canada |
| 145 | linkedin_email,linkedin_hydrator | Data Analyst, Project Controls Technology Services | Provincial Health Services Authority | Burnaby, British Columbia, Canada |
| 104 | linkedin_email,linkedin_hydrator | Data Analyst, Risk and Operational Performance | Kraken | Canada |
| 121 | linkedin_email,linkedin_hydrator | Data Business Analyst - Coquitlam | Natural Factors | Coquitlam, British Columbia, Canada |
| 107 | linkedin_email,linkedin_hydrator | Data Engineer | DarkVision | North Vancouver, British Columbia, Canada |
| 110 | linkedin_email,linkedin_hydrator | Data Engineer | Remote | CodeGeniusRecruit | Canada |
| 180 | indeed_email,indeed_hydrator | Data Governance and Analytics Senior Systems Analyst |  |  |
| 140 | linkedin_email,linkedin_hydrator | Data Operations Manager | $45/hr Remote | Crossing Hurdles | Canada |
| 79 | linkedin_email,linkedin_hydrator | Data Quality Manager (Master Data), Deloitte Global Operations | Deloitte | Vancouver, British Columbia, Canada |
| 13 | linkedin_email,linkedin_hydrator | Data Science Manager | Deloitte | Vancouver, British Columbia, Canada |
| 135 | linkedin_email,linkedin_hydrator | Data Science Manager, Growth | Stripe | Toronto, Ontario, Canada |
| 8 | linkedin_email,linkedin_hydrator | Data Scientist | Dropbox | Canada |
| 55 | linkedin_email,linkedin_hydrator | Data Scientist | Joveo Ai | Canada |
| 75 | linkedin_email,linkedin_hydrator | data scientist | Altea Healthcare | Burnaby, British Columbia, Canada |
| 97 | linkedin_email,linkedin_hydrator | Data Scientist | Joveo Ai | Canada |
| 106 | linkedin_email,linkedin_hydrator | Data Scientist | Alquemy Search & Consulting | Vancouver, British Columbia, Canada |
| 133 | linkedin_email,linkedin_hydrator | Data Scientist | Alquemy Search & Consulting | Vancouver, British Columbia, Canada |
| 148 | linkedin_email,linkedin_hydrator | Data Scientist | Alquemy Search & Consulting | Vancouver, British Columbia, Canada |
| 166 | indeed_email,indeed_hydrator | Data Scientist |  |  |
| 56 | linkedin_email,linkedin_hydrator | Data Scientist (Remote) | Jobs Ai | Canada |
| 7 | linkedin_email,linkedin_hydrator | Data Scientist Specialist (Lending) | Jobgether | Canada |
| 40 | linkedin_email,linkedin_hydrator | Data Scientist, AI/ML Platform | KOHO | Canada |
| 21 | linkedin_email,linkedin_hydrator | Data Scientist, Investment Data | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 168 | indeed_email,indeed_hydrator | Design Engineer - CANADA (Remote) |  |  |
| 14 | linkedin_email,linkedin_hydrator | Développeur principal ou développeuse principale (IA, apprentissage-machine, solutions d'IA générati | TELUS | Burnaby, British Columbia, Canada |
| 157 | indeed_email,indeed_hydrator | Engineering Tech Lead (vMetal) |  |  |
| 45 | linkedin_email,linkedin_hydrator | Intermediate II Software Developer - Artificial Intelligence | Global Relay | Vancouver, British Columbia, Canada |
| 134 | linkedin_email,linkedin_hydrator | Lead Data Scientist | Cohere | Canada |
| 65 | linkedin_email,linkedin_hydrator | Lead Data Scientist - Search, Data & Insights (D&I) | Electronic Arts (EA) | Vancouver, British Columbia, Canada |
| 158 | indeed_email,indeed_hydrator | Lead Engineer |  |  |
| 137 | linkedin_email,linkedin_hydrator | Lead Machine Learning Engineer (Team Lead) | Datatonic | Canada |
| 173 | indeed_email,indeed_hydrator | Lead Platform Engineer - Canada |  |  |
| 1 | linkedin_email,linkedin_hydrator | Machine Learning Engineer | Datatonic | Canada |
| 105 | linkedin_email,linkedin_hydrator | Machine Learning Engineer | TRAFFIX | Toronto, Ontario, Canada |
| 48 | linkedin_email,linkedin_hydrator | Machine Learning Engineer (Remote) | Jobs Ai | Canada |
| 31 | linkedin_email,linkedin_hydrator | Machine Learning Scientist | DarkVision | North Vancouver, British Columbia, Canada |
| 62 | linkedin_email,linkedin_hydrator | Machine Learning Software Engineer | RBC | Toronto, Ontario, Canada |
| 111 | linkedin_email,linkedin_hydrator | Manager Data Analytics and Reporting | BMO | Toronto, Ontario, Canada |
| 116 | linkedin_email,linkedin_hydrator | Manager, AI/ML Models - Financial Engineering & Modeling | Deloitte | Toronto, Ontario, Canada |
| 132 | linkedin_email,linkedin_hydrator | Manager, Business Intelligence & Data Analytics | Douglas College | New Westminster, British Columbia, Canada |
| 76 | linkedin_email,linkedin_hydrator | Manager, Data Analytics | Fasken | Vancouver, British Columbia, Canada |
| 117 | linkedin_email,linkedin_hydrator | Manager, Data Architecture and AI | Intact | Montreal, Quebec, Canada |
| 84 | linkedin_email,linkedin_hydrator | Manager, Data Science, Marketing Analytics | Match | Vancouver, British Columbia, Canada |
| 85 | linkedin_email,linkedin_hydrator | Manager, Financial Crimes- Data Analytics | KPMG Canada | Vancouver, British Columbia, Canada |
| 136 | linkedin_email,linkedin_hydrator | Manager, Machine Learning Engineering (Fraud) | Affirm | Kelowna, British Columbia, Canada |
| 30 | linkedin_email,linkedin_hydrator | Managing Consultant SAP Analytics - BDC Architect | IBM | Vancouver, British Columbia, Canada |
| 100 | linkedin_email,linkedin_hydrator | Member of Technical Staff, MLE | Cohere | Toronto, Ontario, Canada |
| 49 | linkedin_email,linkedin_hydrator | Member of Technical Staff, Search | Cohere | Toronto, Ontario, Canada |
| 154 | linkedin_email,linkedin_hydrator | Performance Measurement Specialist | BC College of Nurses and Midwives | Vancouver, British Columbia, Canada |
| 123 | linkedin_email,linkedin_hydrator | Portfolio Research Analyst, Quantitative Equities | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 81 | linkedin_email,linkedin_hydrator | Principal AI Engineer | ABC Fitness | Vancouver, British Columbia, Canada |
| 177 | indeed_email,indeed_hydrator | Principal Developer |  |  |
| 151 | linkedin_email,linkedin_hydrator | Principal Engineer, AI & ML Solutions, GFT | RBC | Toronto, Ontario, Canada |
| 160 | indeed_email,indeed_hydrator | Programmer Analyst I |  |  |
| 94 | linkedin_email,linkedin_hydrator | Quantitative Data Analyst, Investment Data | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 93 | linkedin_email,linkedin_hydrator | Quantitative Equity Analyst – Data Science | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 96 | linkedin_email,linkedin_hydrator | Quantitative Equity Research, Alpha | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 95 | linkedin_email,linkedin_hydrator | Quantitative Equity Technology, Quantitative Developer | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 122 | linkedin_email,linkedin_hydrator | Quantitative Researcher, Fixed Income | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 155 | linkedin_email,linkedin_hydrator | Relevance Engineer – Enterprise Search & AI Hybrid | Cisco | Vancouver, British Columbia, Canada |
| 112 | linkedin_email,linkedin_hydrator | Remote Quantitative Analyst (Finance) - 75403 | Turing | Canada |
| 113 | linkedin_email,linkedin_hydrator | Remote Quantitative Analyst (Finance) - 75403 | Turing | Toronto, Ontario, Canada |
| 28 | linkedin_email,linkedin_hydrator | Research Analyst | Colliers | Vancouver, British Columbia, Canada |
| 98 | linkedin_email,linkedin_hydrator | Research And Development Specialist | Work Consulting | Canada |
| 131 | linkedin_email,linkedin_hydrator | Research Engineer | The University of British Columbia | Vancouver, British Columbia, Canada |
| 167 | indeed_email,indeed_hydrator | Research Scientist |  |  |
| 87 | linkedin_email,linkedin_hydrator | Senior AI Solutions Engineer | Connor, Clark & Lunn Financial Group (CC&L) | Vancouver, British Columbia, Canada |
| 125 | linkedin_email,linkedin_hydrator | Senior AI/ML Engineer | CyberCoders | Toronto, Ontario, Canada |
| 181 | indeed_email,indeed_hydrator | Senior Analytics Engineer, Analytics Enablement |  |  |
| 72 | linkedin_email,linkedin_hydrator | Senior Applied Researcher AI/ML ( CAD) | PointClickCare | Canada |
| 164 | indeed_email,indeed_hydrator | Senior Business Analyst |  |  |
| 77 | linkedin_email,linkedin_hydrator | Senior Data Analyst | Bird Construction | Vancouver, British Columbia, Canada |
| 139 | linkedin_email,linkedin_hydrator | Senior Data Analyst | Coalition, Inc. | Toronto, Ontario, Canada |
| 150 | linkedin_email,linkedin_hydrator | Senior Data Analyst | Bird Construction | Richmond, British Columbia, Canada |
| 26 | linkedin_email,linkedin_hydrator | Senior Data Analyst - Data & Insights | Electronic Arts (EA) | Vancouver, British Columbia, Canada |
| 80 | linkedin_email,linkedin_hydrator | Senior Data Analyst, Core | Match Group | Vancouver, British Columbia, Canada |
| 161 | indeed_email,indeed_hydrator | Senior Data Engineer |  |  |
| 115 | linkedin_email,linkedin_hydrator | Senior Data Engineer, GFT | RBC | Vancouver, British Columbia, Canada |
| 78 | linkedin_email,linkedin_hydrator | Senior Data Product Analyst (1-Year Contract) | BC Financial Services Authority | Vancouver, British Columbia, Canada |
| 15 | linkedin_email,linkedin_hydrator | Senior Data Scientist | Fortra | Canada |
| 27 | linkedin_email,linkedin_hydrator | Senior Data Scientist | Clio | Vancouver, British Columbia, Canada |
| 43 | linkedin_email,linkedin_hydrator | Senior Data Scientist | Autodesk | Toronto, Ontario, Canada |
| 44 | linkedin_email,linkedin_hydrator | Senior Data Scientist | Clio | Toronto, Ontario, Canada |
| 153 | linkedin_email,linkedin_hydrator | Senior Data Scientist | Deloitte | Vancouver, British Columbia, Canada |
| 102 | linkedin_email,linkedin_hydrator | Senior Data Scientist - Agentic AI products | Rockwell Automation | Brampton, Ontario, Canada |
| 142 | linkedin_email,linkedin_hydrator | Senior Data Scientist - GenAI | Cover Genius | Vancouver, British Columbia, Canada |
| 144 | linkedin_email,linkedin_hydrator | Senior Data Scientist - Shopping Experience (Search) | Instacart | Canada |
| 16 | linkedin_email,linkedin_hydrator | Senior Data Scientist, AI Native (Growth) | Life360 | Canada |
| 39 | linkedin_email,linkedin_hydrator | Senior Data Scientist, Finance & Market Risk | Wealthsimple | Canada |
| 42 | linkedin_email,linkedin_hydrator | Senior Data Scientist, People Analytics | Thumbtack | Ontario, Canada |
| 11 | linkedin_email,linkedin_hydrator | Senior Developer (AI/ML/Gen AI Solutions) | TELUS | Burnaby, British Columbia, Canada |
| 86 | linkedin_email,linkedin_hydrator | Senior Developer, Enterprise AI | Clio | Vancouver, British Columbia, Canada |
| 170 | indeed_email,indeed_hydrator | Senior Developer, Fullstack - Canada Pod |  |  |
| 89 | linkedin_email,linkedin_hydrator | Senior Development Manager – Modernization and AI Transformation | RBC | Toronto, Ontario, Canada |
| 159 | indeed_email,indeed_hydrator | Senior Engineer |  |  |
| 91 | linkedin_email,linkedin_hydrator | Senior Engineering Manager, AI Agents | Asana | Vancouver, British Columbia, Canada |
| 69 | linkedin_email,linkedin_hydrator | Senior Machine Learning / Computer Vision Applied Scientist | Apera AI | Vancouver, British Columbia, Canada |
| 18 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer | FreshBooks | Toronto, Ontario, Canada |
| 66 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer | Alignerr | Vancouver, British Columbia, Canada |
| 82 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer | BDO Canada | Vancouver, British Columbia, Canada |
| 41 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer (Remote) | Jobs Ai | Canada |
| 68 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer - Generative AI Team | EA SPORTS | Vancouver, British Columbia, Canada |
| 19 | linkedin_email,linkedin_hydrator | Senior Machine Learning Engineer, Ranking - Quora (Remote) | Quora | Canada |
| 67 | linkedin_email,linkedin_hydrator | Senior Machine Learning Expert | Alignerr | Vancouver, British Columbia, Canada |
| 143 | linkedin_email,linkedin_hydrator | Senior Machine Learning Scientist | ada CX | Canada |
| 12 | linkedin_email,linkedin_hydrator | Senior Manager / Manager, Data Science | Vancity | Vancouver, British Columbia, Canada |
| 118 | linkedin_email,linkedin_hydrator | Senior Manager, Solutions Architecture - Data & AI | TELUS Digital | Ontario, Canada |
| 119 | linkedin_email,linkedin_hydrator | Senior Manager, Solutions Architecture - Data & AI | TELUS Digital | Calgary, Alberta, Canada |
| 51 | linkedin_email,linkedin_hydrator | Senior Principal Machine Learning Engineer | Autodesk | Canada |
| 156 | linkedin_email,linkedin_hydrator | Senior Quantitative Risk Specialist | Coast Capital Savings | Surrey, British Columbia, Canada |
| 35 | linkedin_email,linkedin_hydrator | Senior R&D Engineer | Synopsys Inc | Vancouver, British Columbia, Canada |
| 114 | linkedin_email,linkedin_hydrator | Senior Research Analyst | CIBC | Toronto, Ontario, Canada |
| 71 | linkedin_email,linkedin_hydrator | Senior Research Scientist, Cohere Labs | Cohere | Canada |
| 33 | linkedin_email,linkedin_hydrator | Senior Software Engineer - Machine Learning | Electronic Arts (EA) | Vancouver, British Columbia, Canada |
| 61 | linkedin_email,linkedin_hydrator | Senior Software Engineer, AI (Agents) | Klue | Vancouver, British Columbia, Canada |
| 176 | indeed_email,indeed_hydrator | Senior Web Developer | Canada | Remote |  |  |
| 83 | linkedin_email,linkedin_hydrator | Senior/Principal Machine Learning Engineer | Workday | Vancouver, British Columbia, Canada |
| 46 | linkedin_email,linkedin_hydrator | Software Development Engineer, Middle Mile Disruption Management | Amazon | Vancouver, British Columbia, Canada |
| 58 | linkedin_email,linkedin_hydrator | Software Development Engineer, Middle Mile P&O | Amazon | Vancouver, British Columbia, Canada |
| 162 | indeed_email,indeed_hydrator | Software Development Manager, Amazon MQ |  |  |
| 70 | linkedin_email,linkedin_hydrator | Sr. AI Threat Researcher | Sophos | Canada |
| 120 | linkedin_email,linkedin_hydrator | Sr. Data Analyst | Aecon Group Inc. | Vancouver, British Columbia, Canada |
| 138 | linkedin_email,linkedin_hydrator | Sr. Data Scientist, Alexa Connections | Amazon | Vancouver, British Columbia, Canada |
| 17 | linkedin_email,linkedin_hydrator | Sr. ML Data Scientist (LIME/SHAP) | Insight Global | Canada |
| 169 | indeed_email,indeed_hydrator | Staff Backend Engineer - Databases Tempo | Canada | Remote |  |  |
| 73 | linkedin_email,linkedin_hydrator | Staff Data Scientist | Northbeam | Canada |
| 149 | linkedin_email,linkedin_hydrator | Staff Data Scientist | TEEMA | Vancouver, British Columbia, Canada |
| 175 | indeed_email,indeed_hydrator | Staff Developer |  |  |
| 178 | indeed_email,indeed_hydrator | Staff Developer |  |  |
| 174 | indeed_email,indeed_hydrator | Staff Software Engineer - AI Website Builder - CANADA (Remote) |  |  |
| 38 | linkedin_email,linkedin_hydrator | Statistician | Alimentiv | Toronto, Ontario, Canada |
| 127 | linkedin_email,linkedin_hydrator | Transportation Data Scientist | Jacobs | Burnaby, British Columbia, Canada |

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
