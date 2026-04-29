# TASK-M2-006 — Full Extraction Quality Review (2026-04-28)

**C19-passed postings analyzed**: 168  
**Pre-flagged issues**: 34 (20%)  
**Missing extractions** (hydration failed or no cache): 21

## Flag legend
- `CO?` company is staffing/job-board firm
- `SEN?` seniority Mid but title says Senior/Lead/Staff/Principal/MTS
- `LOC?` location = Other
- `TEAM?` team NULL but title has comma-separated suffix
- `NOJD` no full_jd / `NOEXT` no extraction

## Flag distribution
- `NOJD`: 21
- `CO?`: 16
- `LOC?`: 13
- `TEAM?`: 6
- `SEN?`: 2

## Full extraction table

| Flags | ID | Email Title | LLM Title | Company | Seniority | Location | Team |
|-------|----|-------------|-----------|---------|-----------|----------|------|
|  | 81 | Principal AI Engineer | Principal AI Engineer | ABC Fitness | Principal | Vancouver | NULL |
|  | 143 | Senior Machine Learning Scientist | Senior Machine Learning Scientist | Ada | Senior | Remote — Canada | Product Development |
|  | 25 | Data Analyst | Data Analyst | ADF Medical | Mid | Remote — Canada | Analytics & Business Intellige |
|  | 120 | Sr. Data Analyst | Data Analyst | Aecon | Senior | Vancouver | Data Governance |
| LOC? | 136 | Manager, Machine Learning Engineering (Fraud) | Manager, Machine Learning Engineering | Affirm | Manager | Other | Fraud Machine Learning |
|  | 66 | Senior Machine Learning Engineer | Senior Machine Learning Engineer | Alignerr | Senior | Remote — Canada | NULL |
|  | 67 | Senior Machine Learning Expert | Senior Machine Learning Expert | Alignerr | Senior | Remote — Canada | NULL |
|  | 38 | Statistician | Statistician | Alimentiv | Mid | Toronto | Analysis Services |
| CO? | 106 | Data Scientist | Data Scientist | Alquemy Search & Consulti | Mid | Vancouver | NULL |
| CO? | 133 | Data Scientist | Data Scientist | Alquemy Search & Consulti | Mid | Vancouver | NULL |
| CO? | 148 | Data Scientist | Data Scientist | Alquemy Search & Consulti | Mid | Vancouver | NULL |
|  | 75 | data scientist | Data Scientist | Altea Healthcare | Mid | Vancouver | NULL |
|  | 46 | Software Development Engineer, Middle Mile Di | Software Development Engineer | Amazon | Mid | Vancouver | Middle Mile Transportation Tec |
|  | 58 | Software Development Engineer, Middle Mile P& | Software Development Engineer | Amazon | Mid | Vancouver | Middle Mile Planning and Optim |
|  | 88 | Applied Scientist, Private Brands Discovery | Applied Scientist | Amazon | Mid | Vancouver | Private Brands Discovery |
|  | 138 | Sr. Data Scientist, Alexa Connections | Data Scientist | Amazon | Senior | Vancouver | Alexa Connections |
|  | 69 | Senior Machine Learning / Computer Vision App | Senior Machine Learning / Computer Visio | Apera AI | Senior | Vancouver | AI |
|  | 91 | Senior Engineering Manager, AI Agents | Engineering Manager, AI Agents | Asana | Manager | Vancouver | Agent Orchestration |
|  | 130 | AI Automation Engineer | AI Automation Engineer | Aspire Software | Mid | Remote — Canada | NULL |
|  | 43 | Senior Data Scientist | Senior Data Scientist | Autodesk | Senior | Toronto | Platform Strategy and Emerging |
|  | 51 | Senior Principal Machine Learning Engineer | Senior Principal Machine Learning Engine | Autodesk | Principal | Remote — Canada | NULL |
|  | 146 | Data Analyst | Data Analyst | Axiom Builders | Mid | Vancouver | NULL |
|  | 154 | Performance Measurement Specialist | Performance Measurement Specialist | BC College of Nurses and  | Mid | Hybrid — Vancouver | Research & Evaluation |
|  | 78 | Senior Data Product Analyst (1-Year Contract) | Senior Data Product Analyst | BC Financial Services Aut | Senior | Vancouver | NULL |
|  | 82 | Senior Machine Learning Engineer | Senior Machine Learning Engineer | BDO | Senior | Vancouver | Technology Advisory Services |
|  | 77 | Senior Data Analyst | Senior Data Analyst | Bird Construction | Senior | Vancouver | Business Intelligence & Analyt |
|  | 150 | Senior Data Analyst | Senior Data Analyst | Bird Construction | Senior | Vancouver | Business Intelligence & Analyt |
|  | 111 | Manager Data Analytics and Reporting | Manager Data Analytics and Reporting | BMO | Manager | Hybrid — Toronto | NULL |
|  | 152 | Associate AI Evaluation Scientist | Associate AI Evaluation Scientist | BMO | Mid | Vancouver | Applied AI |
|  | 53 | AI/ML ENGINEER | AI/ML Engineer | Boundary AI | Mid | Remote — Canada | NULL |
|  | 114 | Senior Research Analyst | Senior Research Analyst | CIBC | Senior | Toronto | Multi-Asset and Currency Resea |
|  | 155 | Relevance Engineer – Enterprise Search & AI H | Relevance Engineer | Cisco | Mid | Hybrid — Vancouver | Enterprise Search |
|  | 27 | Senior Data Scientist | Senior Data Scientist | Clio | Senior | Vancouver | Product |
|  | 44 | Senior Data Scientist | Senior Data Scientist | Clio | Senior | Vancouver | Product |
|  | 86 | Senior Developer, Enterprise AI | Senior Developer, Enterprise AI | Clio | Senior | Vancouver | IT |
|  | 9 | Applied Scientist II | Applied Scientist II | Coalition | Mid | Toronto | NULL |
|  | 10 | Applied Scientist II | Applied Scientist II | Coalition | Mid | Toronto | NULL |
|  | 139 | Senior Data Analyst | Senior Data Analyst | Coalition | Senior | Toronto | NULL |
| LOC? | 156 | Senior Quantitative Risk Specialist | Senior Quantitative Risk Specialist | Coast Capital | Senior | Other | NULL |
|  | 110 | Data Engineer \| Remote | Data Engineer | CodeGeniusRecruit | Mid | Remote — Canada | NULL |
| SEN? | 49 | Member of Technical Staff, Search | Member of Technical Staff, Search | Cohere | Mid | Toronto | Search |
|  | 71 | Senior Research Scientist, Cohere Labs | Senior Research Scientist | Cohere | Senior | Remote — Canada | Cohere Labs |
| SEN? | 100 | Member of Technical Staff, MLE | Member of Technical Staff, MLE | Cohere | Mid | Toronto | MLE |
|  | 134 | Lead Data Scientist | Lead Data Scientist | Cohere | Lead | Remote — Canada | Analytics and Data Insights |
|  | 28 | Research Analyst | Research Analyst | Colliers | Mid | Hybrid — Vancouver | Research |
| TEAM? | 24 | Algorithm Engineer, AI | Algorithm Engineer | Comm100 | Mid | Vancouver | NULL |
|  | 20 | AI Solutions Engineer | AI Solutions Engineer | Connor, Clark & Lunn Fina | Mid | Hybrid — Vancouver | IS Department |
|  | 21 | Data Scientist, Investment Data | Data Scientist | Connor, Clark & Lunn Fina | Mid | Vancouver | Quantitative Equity Team |
|  | 87 | Senior AI Solutions Engineer | Senior AI Solutions Engineer | Connor, Clark & Lunn Fina | Senior | Vancouver | AI Enablement |
|  | 93 | Quantitative Equity Analyst – Data Science | Quantitative Equity Analyst | Connor, Clark & Lunn Fina | Mid | Vancouver | Quantitative Equities Team |
|  | 94 | Quantitative Data Analyst, Investment Data | Quantitative Data Analyst | Connor, Clark & Lunn Fina | Mid | Vancouver | Quantitative Equity Team |
| TEAM? | 95 | Quantitative Equity Technology, Quantitative  | Quantitative Developer | Connor, Clark & Lunn Fina | Mid | Vancouver | NULL |
|  | 96 | Quantitative Equity Research, Alpha | Quantitative Research Analyst | Connor, Clark & Lunn Fina | Mid | Vancouver | Quantitative Equity |
|  | 122 | Quantitative Researcher, Fixed Income | Quantitative Researcher | Connor, Clark & Lunn Fina | Mid | Hybrid — Vancouver | Fixed Income Team |
|  | 123 | Portfolio Research Analyst, Quantitative Equi | Portfolio Research Analyst | Connor, Clark & Lunn Fina | Mid | Vancouver | Quantitative Equity Team |
|  | 142 | Senior Data Scientist - GenAI | Senior Data Scientist | Cover Genius | Senior | Vancouver | Central AI Hub |
| CO? | 60 | Data Analyst \| $80/hr Remote | Data Analyst | Crossing Hurdles | Mid | Remote — Canada | NULL |
| CO? | 124 | AI / ML Engineer \| Remote | AI Engineer | Crossing Hurdles | Mid | Remote — Canada | NULL |
| CO? | 140 | Data Operations Manager \| $45/hr Remote | Data Operations Manager | Crossing Hurdles | Manager | Remote — Canada | NULL |
|  | 125 | Senior AI/ML Engineer | Senior AI/ML Engineer | CyberCoders | Senior | Remote — Canada | NULL |
| LOC? | 31 | Machine Learning Scientist | Machine Learning Scientist | DarkVision | Mid | Other | Imaging & AI |
| LOC? | 107 | Data Engineer | Data Engineer | DarkVision | Mid | Other | Imaging & AI |
|  | 1 | Machine Learning Engineer | Machine Learning Engineer | Datatonic | Senior | Remote — Canada | NULL |
|  | 137 | Lead Machine Learning Engineer (Team Lead) | Lead Machine Learning Engineer | Datatonic | Lead | Remote — Canada | Machine Learning |
|  | 13 | Data Science Manager | Data Science Manager | Deloitte | Manager | Hybrid — Vancouver | Artificial Intelligence |
|  | 79 | Data Quality Manager (Master Data), Deloitte  | Data Quality Manager | Deloitte | Manager | Vancouver | Global Data Integration & Serv |
|  | 116 | Manager, AI/ML Models - Financial Engineering | Manager, AI/ML Models - Financial Engine | Deloitte | Manager | Hybrid — Toronto | Risk, Regulatory & Forensics |
|  | 153 | Senior Data Scientist | Senior Data Scientist | Deloitte | Senior | Hybrid — Vancouver | Artificial Intelligence |
|  | 22 | Analytics Engineer | Analytics Engineer | Dialpad | Mid | Vancouver | Data Analysis and QA |
|  | 64 | Applied Scientist | Applied Scientist | Dialpad | Mid | Vancouver | NLP |
|  | 92 | AI Productivity Analyst | AI Productivity Analyst | Dialpad | Mid | Vancouver | AI Transformation |
|  | 128 | AI Productivity Analyst | AI Productivity Analyst | Dialpad | Mid | Vancouver | Product Management |
|  | 90 | AI Solution Architect | AI Solution Architect | Diligent | Senior | Hybrid — Vancouver | Business Applications and Anal |
| TEAM? | 108 | AI/ML Engineer (ChatGPT, Claude, LLM, Agentic | AI/ML Engineer | Diligente Technologies | Mid | Remote — Canada | NULL |
| LOC? TEAM? | 132 | Manager, Business Intelligence & Data Analyti | Manager, Business Intelligence & Data An | Douglas College | Manager | Other | NULL |
| LOC? | 8 | Data Scientist | Data Scientist | Dropbox | Mid | Other | Data Science |
|  | 68 | Senior Machine Learning Engineer - Generative | Senior Machine Learning Engineer | EA SPORTS | Senior | Vancouver | Generative AI Team |
|  | 26 | Senior Data Analyst - Data & Insights | Senior Data Analyst | Electronic Arts | Senior | Vancouver | Data and Insights |
|  | 33 | Senior Software Engineer - Machine Learning | Senior Software Engineer - Machine Learn | Electronic Arts | Senior | Vancouver | NULL |
|  | 63 | AI Enablement Engineer | AI Enablement Engineer | Electronic Arts | Mid | Vancouver | EA Experiences |
|  | 65 | Lead Data Scientist - Search, Data & Insights | Lead Data Scientist | Electronic Arts | Lead | Vancouver | Data and Insights |
|  | 76 | Manager, Data Analytics | Manager, Data Analytics | Fasken | Manager | Hybrid — Vancouver | Data Analytics & Engineering |
|  | 15 | Senior Data Scientist | Senior Data Scientist | Fortra | Senior | Remote — Canada | NULL |
|  | 18 | Senior Machine Learning Engineer | Senior Machine Learning Engineer | FreshBooks | Senior | Toronto | NULL |
|  | 5 | AI ML Engineer | AI/ML Engineer | Galent | Mid | Remote — Canada | NULL |
|  | 6 | Artificial Intelligence Engineer | Artificial Intelligence Engineer | Galent | Mid | Remote — Canada | NULL |
|  | 45 | Intermediate II Software Developer - Artifici | Intermediate Software Developer | Global Relay | Mid | Vancouver | Engineering |
|  | 30 | Managing Consultant SAP Analytics - BDC Archi | Managing Consultant SAP Analytics - BDC  | IBM | Senior | Vancouver | NULL |
|  | 17 | Sr. ML Data Scientist (LIME/SHAP) | ML Data Scientist | Insight Global | Senior | Remote — Canada | NULL |
|  | 144 | Senior Data Scientist - Shopping Experience ( | Senior Data Scientist | Instacart | Senior | Remote — Canada | Shopping Experience |
|  | 117 | Manager, Data Architecture and AI | Manager, Data Architecture and AI | Intact | Manager | Montreal | Intact Lab |
|  | 127 | Transportation Data Scientist | Transportation Data Scientist | Jacobs | Mid | Vancouver | Data and Metrics Quality |
|  | 7 | Data Scientist Specialist (Lending) | Data Scientist | Jobgether | Mid | Remote — Canada | NULL |
| CO? | 41 | Senior Machine Learning Engineer (Remote) | Senior Machine Learning Engineer | Jobs Ai | Senior | Remote — Canada | NULL |
| CO? | 48 | Machine Learning Engineer (Remote) | Machine Learning Engineer | Jobs Ai | Mid | Remote — Canada | NULL |
| CO? | 50 | Bioinformatics Scientist (Remote) | Bioinformatics Scientist | Jobs Ai | Mid | Remote — Canada | NULL |
| CO? | 52 | AI Engineer (Remote) | AI Engineer | Jobs AI | Mid | Remote — Canada | NULL |
| CO? | 56 | Data Scientist (Remote) | Data Scientist | Jobs AI | Mid | Remote — Canada | NULL |
| CO? | 59 | Data Analyst (Remote) | Data Analyst | Jobs Ai | Mid | Remote — Canada | NULL |
| CO? | 54 | Agentic AI Engineer | Agentic AI Engineer | Joveo | Mid | Remote — Canada | NULL |
| CO? | 55 | Data Scientist | Data Scientist | Joveo | Mid | Remote — Canada | NULL |
| CO? | 97 | Data Scientist | Data Scientist | Joveo | Mid | Remote — Canada | NULL |
|  | 61 | Senior Software Engineer, AI (Agents) | Senior Software Engineer | Klue | Senior | Vancouver | Engineering |
|  | 40 | Data Scientist, AI/ML Platform | Data Scientist | KOHO | Mid | Remote — Canada | AI/ML Platform |
|  | 85 | Manager, Financial Crimes- Data Analytics | Manager, Financial Crimes - Data Analyti | KPMG | Manager | Vancouver | National Financial Crimes Cent |
|  | 104 | Data Analyst, Risk and Operational Performanc | Data Analyst | Kraken | Mid | Remote — Canada | Core Services |
|  | 141 | Data Analyst, Growth | Data Analyst, Growth | Kraken | Mid | Remote — Canada | Data |
|  | 16 | Senior Data Scientist, AI Native (Growth) | Senior Data Scientist | Life360 | Senior | Remote — Canada | Data Science |
|  | 2 | AI Engineer (Remote) | AI Engineer | Lumenalta | Mid | Remote — Canada | NULL |
|  | 4 | AI Engineer (Remote) | AI Engineer | Lumenalta | Mid | Remote — Canada | NULL |
|  | 84 | Manager, Data Science, Marketing Analytics | Manager, Data Science, Marketing Analyti | Match | Manager | Vancouver | Analytics Team |
|  | 80 | Senior Data Analyst, Core | Senior Data Analyst | Match Group | Senior | Vancouver | Core Data |
| LOC? | 121 | Data Business Analyst - Coquitlam | Data Business Analyst | Natural Factors | Mid | Other | NULL |
|  | 73 | Staff Data Scientist | Staff Data Scientist | Northbeam | Staff | Remote — Canada | Data Science |
|  | 129 | AI Development Engineer - Remote | AI Development Engineer | NTT DATA | Mid | Remote — Canada | NULL |
| LOC? | 72 | Senior Applied Researcher AI/ML ( CAD) | Senior Applied Researcher | PointClickCare | Senior | Other | Advanced Technology / Applied  |
|  | 145 | Data Analyst, Project Controls Technology Ser | Data Analyst | Provincial Health Service | Mid | Vancouver | Project Controls |
|  | 19 | Senior Machine Learning Engineer, Ranking - Q | Senior Machine Learning Engineer | Quora | Senior | Remote — Canada | Engineering |
|  | 62 | Machine Learning Software Engineer | Machine Learning Software Engineer | RBC | Mid | Toronto | Borealis |
|  | 89 | Senior Development Manager – Modernization an | Senior Development Manager | RBC | Senior | Toronto | Technology and Operations |
|  | 115 | Senior Data Engineer, GFT | Senior Data Engineer | RBC | Senior | Vancouver | Global Functions Technology |
|  | 151 | Principal Engineer, AI & ML Solutions, GFT | Principal Engineer, AI & ML Solutions | RBC | Principal | Toronto | Global Functions Technology |
|  | 102 | Senior Data Scientist - Agentic AI products | Senior Data Scientist | Rockwell Automation | Senior | Toronto | Data Science & Innovation |
| LOC? | 74 | AI Sim - Staff ML Research Engineer | AI Sim - Staff ML Research Engineer | SandboxAQ | Staff | Other | AI Sim R&D |
|  | 70 | Sr. AI Threat Researcher | AI Threat Researcher | Sophos | Senior | Remote — Canada | X-Ops Insights |
|  | 126 | Associate Data Scientist - User Fraud | Associate Data Scientist | Spotify | Mid | Toronto | Data Science |
|  | 135 | Data Science Manager, Growth | Data Science Manager | Stripe | Manager | Toronto | Growth Data Science |
|  | 35 | Senior R&D Engineer | R&D Engineer | Synopsys | Senior | Vancouver | R&D Engineering |
|  | 149 | Staff Data Scientist | Staff Data Scientist | TEEMA | Staff | Vancouver | NULL |
|  | 11 | Senior Developer (AI/ML/Gen AI Solutions) | Senior Developer | TELUS | Senior | Vancouver | AI Accelerator |
|  | 14 | Développeur principal ou développeuse princip | Développeur principal | TELUS | Principal | Vancouver | Accélérateur d’IA |
| LOC? TEAM? | 118 | Senior Manager, Solutions Architecture - Data | Senior Manager, Solutions Architecture - | TELUS Digital | Manager | Other | NULL |
| LOC? TEAM? | 119 | Senior Manager, Solutions Architecture - Data | Senior Manager, Solutions Architecture - | TELUS Digital | Manager | Other | NULL |
| LOC? | 42 | Senior Data Scientist, People Analytics | Senior Data Scientist | Thumbtack | Senior | Other | People Data Science |
| LOC? | 101 | Applied Scientist, Customer Growth | Applied Scientist, Customer Growth | Thumbtack | Mid | Other | Applied Science |
|  | 105 | Machine Learning Engineer | Machine Learning Engineer | Traffix | Mid | Toronto | NULL |
|  | 147 | Data Analyst - FTT | Data Analyst | TransLink | Mid | Hybrid — Vancouver | Data Management Team |
|  | 112 | Remote Quantitative Analyst (Finance) - 75403 | Quantitative Analyst | Turing | Mid | Remote — Canada | NULL |
|  | 113 | Remote Quantitative Analyst (Finance) - 75403 | Quantitative Analyst | Turing | Mid | Remote — Canada | NULL |
|  | 131 | Research Engineer | Research Engineer | University of British Col | Mid | Vancouver | Research Group \| Olson Lab \| D |
|  | 12 | Senior Manager / Manager, Data Science | Senior Manager, Data Science | Vancity | Senior | Vancouver | AI Centre of Excellence |
|  | 23 | AI Software Developer (Healthcare Systems & A | AI Software Developer | Vancouver Psychology Cent | Mid | Vancouver | NULL |
|  | 39 | Senior Data Scientist, Finance & Market Risk | Senior Data Scientist | Wealthsimple | Senior | Remote — Canada | Finance and Market Risk Data S |
|  | 98 | Research And Development Specialist | Research And Development Specialist | Work Consulting | Mid | Remote — Canada | NULL |
|  | 83 | Senior/Principal Machine Learning Engineer | Senior/Principal Machine Learning Engine | Workday | Senior | Vancouver | Agent Factory |
|  | 57 | AI Specialist - Applied ML Research | AI Specialist - Applied ML Research | Xanadu | Mid | Toronto | AI |
| CO? | 3 | AI/ML Engineer - Remote | AI/ML Engineer | YO HR Consultancy | Mid | Remote — Canada | NULL |
| NOJD | 157 | Engineering Tech Lead (vMetal) |  |  |  |  |  |
| NOJD | 158 | Lead Engineer |  |  |  |  |  |
| NOJD | 159 | Senior Engineer |  |  |  |  |  |
| NOJD | 160 | Programmer Analyst I |  |  |  |  |  |
| NOJD | 161 | Senior Data Engineer |  |  |  |  |  |
| NOJD | 162 | Software Development Manager, Amazon MQ |  |  |  |  |  |
| NOJD | 164 | Senior Business Analyst |  |  |  |  |  |
| NOJD | 165 | AI Senior Machine Learning Engineer, General  |  |  |  |  |  |
| NOJD | 166 | Data Scientist |  |  |  |  |  |
| NOJD | 167 | Research Scientist |  |  |  |  |  |
| NOJD | 168 | Design Engineer - CANADA (Remote) |  |  |  |  |  |
| NOJD | 169 | Staff Backend Engineer - Databases Tempo \| Ca |  |  |  |  |  |
| NOJD | 170 | Senior Developer, Fullstack - Canada Pod |  |  |  |  |  |
| NOJD | 173 | Lead Platform Engineer - Canada |  |  |  |  |  |
| NOJD | 174 | Staff Software Engineer - AI Website Builder  |  |  |  |  |  |
| NOJD | 175 | Staff Developer |  |  |  |  |  |
| NOJD | 176 | Senior Web Developer \| Canada \| Remote |  |  |  |  |  |
| NOJD | 177 | Principal Developer |  |  |  |  |  |
| NOJD | 178 | Staff Developer |  |  |  |  |  |
| NOJD | 180 | Data Governance and Analytics Senior Systems  |  |  |  |  |  |
| NOJD | 181 | Senior Analytics Engineer, Analytics Enableme |  |  |  |  |  |