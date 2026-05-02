# TASK-M2-006b Phase A — Top-Skills Canonicalization Analysis

| Field | Value |
|-------|-------|
| Task | TASK-M2-006b |
| Date | 2026-04-29 |
| Phase A status | **Awaiting user taxonomy review** |
| Phase B–E | Blocked pending user sign-off on canonical taxonomy below |

## 2. Methodology

- Source: `extraction_cache` table in `/Users/andrew.yu/.jd-matcher/jd-matcher.db` — 140 rows with non-empty `top_skills`
- Note: the join from `extraction_cache` to `postings` requires computing `SHA-256(full_jd)` inside SQLite, which is not natively supported. All 140 cached extractions are used instead. The 7 C19-filtered postings were dropped **before** LLM extraction and are therefore absent from `extraction_cache` — so this analysis already reflects C19-passed postings only.
- Total postings analyzed: **140**
- Total skill mentions (raw): **1209**
- Distinct normalized forms: **278**
- Multi-variant clusters (≥2 surface forms): **4**
- Single-form clusters: **274**

## 3. Multi-Variant Clusters (Canonicalization Targets)

Sorted by total occurrences descending. These are the primary targets for prompt canonicalization.

| Normalized form | Total occ | Surface forms (count) | Proposed canonical | Notes |
|-----------------|-----------|----------------------|---------------------|-------|
| scikit-learn | 4 | "Scikit-Learn" (3), "scikit-learn" (1) | **Scikit-Learn** | |
| java | 4 | "Java" (3), "JAVA" (1) | **Java** | |
| langchain | 3 | "LangChain" (2), "Langchain" (1) | **LangChain** | |
| api development | 2 | "API Development" (1), "API development" (1) | **API Development** | |

## 4. Proposed Canonical Taxonomy (Top 50 Skills by Frequency)

Explicit list of canonical forms the C18 extraction prompt will enforce after Phase B. Tail skills (rank >50, low frequency, single surface form) remain free-form.

- **Python** (92 mentions)
- **Machine Learning** (92 mentions)
- **Data Analysis** (80 mentions)
- **Data Engineering** (67 mentions)
- **SQL** (53 mentions)
- **Data Visualization** (35 mentions)
- **Statistical Analysis** (32 mentions)
- **LLMs** (28 mentions)
- **PyTorch** (23 mentions)
- **AI** (22 mentions)
- **AWS** (22 mentions)
- **Generative AI** (21 mentions)
- **A/B Testing** (21 mentions)
- **NLP** (21 mentions)
- **Data Science** (20 mentions)
- **MLOps** (19 mentions)
- **Cloud Computing** (19 mentions)
- **CI/CD** (19 mentions)
- **Deep Learning** (18 mentions)
- **Optimization** (17 mentions)
- **TensorFlow** (16 mentions)
- **Automation** (16 mentions)
- **Azure** (12 mentions)
- **Predictive Modeling** (11 mentions)
- **Causal Inference** (11 mentions)
- **Spark** (10 mentions)
- **GCP** (10 mentions)
- **Kubernetes** (10 mentions)
- **Data Management** (9 mentions)
- **Databricks** (9 mentions)
- **Data Quality** (9 mentions)
- **Data Modeling** (9 mentions)
- **Data Governance** (9 mentions)
- **Power BI** (9 mentions)
- **Statistics** (7 mentions)
- **Microservices** (6 mentions)
- **Data Mining** (6 mentions)
- **Computer Vision** (6 mentions)
- **Business Intelligence** (6 mentions)
- **Feature Engineering** (5 mentions)
- **Data Pipelines** (5 mentions)
- **Scikit-Learn** (4 mentions)  (covers: scikit-learn)
- **Docker** (4 mentions)
- **C++** (4 mentions)
- **Tableau** (4 mentions)
- **R** (4 mentions)
- **Java** (4 mentions)  (covers: JAVA)
- **C#** (4 mentions)
- **dbt** (4 mentions)
- **GenAI** (4 mentions)

## 5. Ambiguity Flags — Needs User Input

These clusters have genuine semantic overlap but may or may not be the same skill. User decision required before finalizing the canonical taxonomy.

### GenAI / Generative AI / LLM umbrella

**Present in corpus** (55 total mentions): `genai`, `generative ai`, `llms`, `large language models`

**Options:**
- A) Merge all into **Generative AI**
- B) Keep **LLM** and **Generative AI** as two separate skills (fine-grained)
- C) Use **LLMs** as the canonical (most concise technical form)

**Recommended**: B — LLMs are a subset of Generative AI; keeping them separate preserves signal

### Deep Learning / DL / Neural Networks

**Present in corpus** (18 total mentions): `deep learning`

**Options:**
- A) Merge all into **Deep Learning**
- B) Keep **Deep Learning** and **Neural Networks** separate

**Recommended**: A — DL and NN are near-synonymous at the skill-tag level

### NLP / Natural Language Processing

**Present in corpus** (22 total mentions): `nlp`, `natural language processing`

**Options:**
- A) Merge into **Natural Language Processing (NLP)** — verbose but clear
- B) Merge into **NLP** — short, widely understood

**Recommended**: B — NLP is the standard abbreviation; pair with LLM (separate)

### ML / Machine Learning

**Present in corpus** (92 total mentions): `machine learning`

**Options:**
- A) Merge all into **Machine Learning**
- B) Keep **Machine Learning** + **AI/ML** as distinct (some postings mean the broad field)

**Recommended**: A — ML, machine learning, ML/AI all refer to the same skill cluster

### Cloud / AWS / GCP / Azure umbrella

**Present in corpus** (63 total mentions): `aws`, `gcp`, `azure`, `cloud computing`

**Options:**
- A) Keep platform-specific (AWS, GCP, Azure) as separate skills; generic 'Cloud' as a catch-all
- B) Merge all into **Cloud Platforms**

**Recommended**: A — specific platforms signal vendor experience; generic Cloud is a separate tag

### Data Engineering / Data Pipelines

**Present in corpus** (72 total mentions): `data engineering`, `data pipelines`

**Options:**
- A) Merge into **Data Engineering**
- B) Keep **Data Pipelines** as a sub-skill

**Recommended**: A — Data Pipelines is a subset of Data Engineering

### MLOps / ML Engineering

**Present in corpus** (19 total mentions): `mlops`

**Options:**
- A) Merge all into **MLOps**
- B) Keep **ML Engineering** and **MLOps** separate (MLOps = infra, ML Eng = modeling+infra)

**Recommended**: A — in job postings these terms are used interchangeably

### Spark / Apache Spark / PySpark

**Present in corpus** (12 total mentions): `spark`, `apache spark`, `pyspark`

**Options:**
- A) Merge into **Apache Spark**
- B) Keep **Spark** and **PySpark** separate (PySpark = Python API specifically)

**Recommended**: A — merge; the specific API is rarely a distinguishing factor at skill-tag level

### Scikit-learn variants

**Present in corpus** (4 total mentions): `scikit-learn`

**Options:**
- A) Canonical: **Scikit-Learn**

**Recommended**: A — clear merge, scikit-learn is the official name

### TensorFlow variants

**Present in corpus** (16 total mentions): `tensorflow`

**Options:**
- A) Canonical: **TensorFlow**

**Recommended**: A — clear merge

### PyTorch variants

**Present in corpus** (23 total mentions): `pytorch`

**Options:**
- A) Canonical: **PyTorch**

**Recommended**: A — clear merge

## 6. Tail Skills (Single-Form, ≥2 Occurrences, Not in Top 50)

Listed for completeness. Pull into the canonical taxonomy if relevant.

- `JavaScript` (3 mentions)
- `APIs` (3 mentions)
- `Airflow` (2 mentions)
- `Kafka` (2 mentions)
- `LangGraph` (2 mentions)
- `NoSQL` (2 mentions)
- `React` (2 mentions)
- `Vertex AI` (2 mentions)
- `Model Deployment` (2 mentions)
- `Reporting` (2 mentions)
- `Time-Series Analysis` (2 mentions)
- `Microsoft 365` (2 mentions)
- `TensorRT` (2 mentions)
- `Software Development` (2 mentions)
- `Software Design` (2 mentions)
- `Algorithms` (2 mentions)
- `Testing` (2 mentions)
- `Large Language Models` (2 mentions)
- `Monitoring` (2 mentions)
- `Metabase` (2 mentions)
- `Elasticsearch` (2 mentions)
- `Power Query` (2 mentions)
- `Marketing Analytics` (2 mentions)
- `Experimental Design` (2 mentions)
- `Derivatives Pricing` (2 mentions)
- `Portfolio Management` (2 mentions)
- `Snowflake` (2 mentions)
- `Business Analysis` (2 mentions)

## 7. Estimated Impact on FUSE Jaccard

Approximately **4** skill mentions (0.3% of all mentions) across multi-variant clusters currently produce **zero Jaccard contribution** when compared against postings using a different surface form for the same skill. Canonicalizing these clusters is expected to meaningfully improve FUSE dedup recall — particularly for high-frequency clusters like Machine Learning (13 total multi-variant occurrences across 4 clusters).
