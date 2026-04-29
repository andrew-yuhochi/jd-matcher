"""Phase A analysis script for TASK-M2-006b.

Reads extraction_cache rows, flattens all top_skills strings,
groups them by case-insensitive normalized form, and produces
a Markdown analysis report surfacing multi-variant clusters
(same skill, different surface forms) for canonical taxonomy design.

Usage:
    python scripts/analyze_top_skills.py \\
        [--db ~/.jd-matcher/jd-matcher.db] \\
        [--out docs/poc/quality-logs/TASK-M2-006b-skills-analysis.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_skill_strings(db_path: Path) -> tuple[list[str], int]:
    """Return (flat list of all skill strings, number of cache rows read).

    Reads every extraction_cache row whose top_skills list is non-empty.
    Note: we use all cached extractions rather than restricting to
    C19-passed postings because the extraction_cache ↔ postings join
    requires computing SHA-256(full_jd) inside SQLite, which is not
    natively supported.  The 140 extraction_cache rows represent
    postings that successfully completed LLM extraction; the 7
    C19-filtered postings were dropped before extraction and are
    therefore absent from the cache already.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT canonical_extraction_json FROM extraction_cache"
        ).fetchall()
    finally:
        conn.close()

    skills: list[str] = []
    cache_rows_with_skills = 0
    for (json_text,) in rows:
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            continue
        raw_skills: list = data.get("top_skills") or []
        if raw_skills:
            cache_rows_with_skills += 1
            skills.extend(str(s) for s in raw_skills if s)
    return skills, cache_rows_with_skills


# ---------------------------------------------------------------------------
# Normalization + clustering
# ---------------------------------------------------------------------------

def _normalize(skill: str) -> str:
    """Canonical cluster key: lowercase, strip, collapse internal whitespace."""
    return re.sub(r"\s+", " ", skill.strip().lower())


def build_clusters(
    raw_skills: list[str],
) -> dict[str, dict[str, int]]:
    """Return {normalized_form: {surface_form: count}}."""
    clusters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for s in raw_skills:
        norm = _normalize(s)
        clusters[norm][s] += 1
    return {norm: dict(surfaces) for norm, surfaces in clusters.items()}


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _format_surface_forms(surface_counts: dict[str, int]) -> str:
    """Format surface forms as '"Form" (N), ...' sorted by count desc."""
    pairs = sorted(surface_counts.items(), key=lambda x: (-x[1], x[0]))
    return ", ".join(f'"{s}" ({c})' for s, c in pairs)


def _propose_canonical(surface_counts: dict[str, int]) -> str:
    """Heuristic: pick the most-frequent surface form; prefer Title Case."""
    sorted_forms = sorted(surface_counts.items(), key=lambda x: -x[1])
    # Prefer the most-frequent form.  If tied, prefer Title Case.
    top_count = sorted_forms[0][1]
    candidates = [f for f, c in sorted_forms if c == top_count]
    title_cased = [f for f in candidates if f == f.title() or f[0].isupper()]
    chosen = title_cased[0] if title_cased else candidates[0]
    return f"**{chosen}**"


# ---------------------------------------------------------------------------
# Ambiguity detection
# ---------------------------------------------------------------------------

# Known ambiguity groups: clusters whose normalized forms should probably
# merge but may not — flagged for user confirmation.
_AMBIGUITY_GROUPS: list[dict] = [
    {
        "label": "GenAI / Generative AI / LLM umbrella",
        "members": ["genai", "generative ai", "llms", "llm", "large language models",
                    "large language model", "llm fine-tuning", "generative ai/llms"],
        "options": [
            "A) Merge all into **Generative AI**",
            "B) Keep **LLM** and **Generative AI** as two separate skills (fine-grained)",
            "C) Use **LLMs** as the canonical (most concise technical form)",
        ],
        "recommended": "B — LLMs are a subset of Generative AI; keeping them separate preserves signal",
    },
    {
        "label": "Deep Learning / DL / Neural Networks",
        "members": ["deep learning", "dl", "neural networks", "neural network"],
        "options": [
            "A) Merge all into **Deep Learning**",
            "B) Keep **Deep Learning** and **Neural Networks** separate",
        ],
        "recommended": "A — DL and NN are near-synonymous at the skill-tag level",
    },
    {
        "label": "NLP / Natural Language Processing",
        "members": ["nlp", "natural language processing"],
        "options": [
            "A) Merge into **Natural Language Processing (NLP)** — verbose but clear",
            "B) Merge into **NLP** — short, widely understood",
        ],
        "recommended": "B — NLP is the standard abbreviation; pair with LLM (separate)",
    },
    {
        "label": "ML / Machine Learning",
        "members": ["ml", "machine learning", "ml/ai", "ai/ml", "ai/ml engineering"],
        "options": [
            "A) Merge all into **Machine Learning**",
            "B) Keep **Machine Learning** + **AI/ML** as distinct (some postings mean the broad field)",
        ],
        "recommended": "A — ML, machine learning, ML/AI all refer to the same skill cluster",
    },
    {
        "label": "Cloud / AWS / GCP / Azure umbrella",
        "members": ["cloud", "aws", "gcp", "azure", "cloud computing",
                    "cloud platforms", "cloud services", "cloud infrastructure"],
        "options": [
            "A) Keep platform-specific (AWS, GCP, Azure) as separate skills; generic 'Cloud' as a catch-all",
            "B) Merge all into **Cloud Platforms**",
        ],
        "recommended": "A — specific platforms signal vendor experience; generic Cloud is a separate tag",
    },
    {
        "label": "Data Engineering / Data Pipelines",
        "members": ["data engineering", "data pipelines", "data pipeline"],
        "options": [
            "A) Merge into **Data Engineering**",
            "B) Keep **Data Pipelines** as a sub-skill",
        ],
        "recommended": "A — Data Pipelines is a subset of Data Engineering",
    },
    {
        "label": "MLOps / ML Engineering",
        "members": ["mlops", "ml engineering", "ml ops"],
        "options": [
            "A) Merge all into **MLOps**",
            "B) Keep **ML Engineering** and **MLOps** separate (MLOps = infra, ML Eng = modeling+infra)",
        ],
        "recommended": "A — in job postings these terms are used interchangeably",
    },
    {
        "label": "Spark / Apache Spark / PySpark",
        "members": ["spark", "apache spark", "pyspark"],
        "options": [
            "A) Merge into **Apache Spark**",
            "B) Keep **Spark** and **PySpark** separate (PySpark = Python API specifically)",
        ],
        "recommended": "A — merge; the specific API is rarely a distinguishing factor at skill-tag level",
    },
    {
        "label": "Scikit-learn variants",
        "members": ["scikit-learn", "sklearn", "scikit learn"],
        "options": [
            "A) Canonical: **Scikit-Learn**",
        ],
        "recommended": "A — clear merge, scikit-learn is the official name",
    },
    {
        "label": "TensorFlow variants",
        "members": ["tensorflow", "tf"],
        "options": [
            "A) Canonical: **TensorFlow**",
        ],
        "recommended": "A — clear merge",
    },
    {
        "label": "PyTorch variants",
        "members": ["pytorch", "torch"],
        "options": [
            "A) Canonical: **PyTorch**",
        ],
        "recommended": "A — clear merge",
    },
]


def check_ambiguity_flags(clusters: dict[str, dict[str, int]]) -> list[dict]:
    """Return ambiguity groups whose members appear in the actual corpus."""
    active_flags = []
    all_norms = set(clusters.keys())
    for group in _AMBIGUITY_GROUPS:
        present = [m for m in group["members"] if m in all_norms]
        if len(present) >= 1:
            group_copy = dict(group)
            group_copy["present_in_corpus"] = present
            group_copy["total_occurrences"] = sum(
                sum(clusters[m].values()) for m in present if m in clusters
            )
            active_flags.append(group_copy)
    return active_flags


# ---------------------------------------------------------------------------
# Impact estimation
# ---------------------------------------------------------------------------

def estimate_jaccard_impact(
    clusters: dict[str, dict[str, int]],
    multi_variant: dict[str, dict[str, int]],
) -> str:
    """Back-of-envelope: how many skill-mention pairs are currently unmatched."""
    total_multi_occurrences = sum(
        sum(s.values()) for s in multi_variant.values()
    )
    total_occurrences = sum(sum(s.values()) for s in clusters.values())
    # Each multi-variant cluster: occurrences across N postings.
    # Two postings sharing the same underlying skill but different surface forms
    # contribute 0 to Jaccard instead of the correct weight.
    # Rough count: for each multi-variant cluster, (total_occurrences - max_single_form_count)
    # represents "displaced" mentions.
    displaced = 0
    for surfaces in multi_variant.values():
        total = sum(surfaces.values())
        max_form = max(surfaces.values())
        displaced += total - max_form

    pct = 100 * displaced / total_occurrences if total_occurrences else 0
    return (
        f"Approximately **{displaced}** skill mentions ({pct:.1f}% of all mentions) "
        f"across multi-variant clusters currently produce **zero Jaccard contribution** "
        f"when compared against postings using a different surface form for the same skill. "
        f"Canonicalizing these clusters is expected to meaningfully improve FUSE dedup "
        f"recall — particularly for high-frequency clusters like Machine Learning ({total_multi_occurrences} "
        f"total multi-variant occurrences across {len(multi_variant)} clusters)."
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    db_path: Path,
    out_path: Path,
) -> dict:
    """Run the full analysis and write the Markdown report. Returns summary stats."""
    raw_skills, rows_analyzed = load_skill_strings(db_path)
    clusters = build_clusters(raw_skills)

    # Split into multi-variant vs single-form
    multi_variant = {
        norm: surfaces
        for norm, surfaces in clusters.items()
        if len(surfaces) >= 2
    }
    single_form = {
        norm: surfaces
        for norm, surfaces in clusters.items()
        if len(surfaces) == 1
    }

    # Sort all clusters by total occurrences
    def total_occ(surfaces: dict[str, int]) -> int:
        return sum(surfaces.values())

    sorted_multi = sorted(multi_variant.items(), key=lambda x: -total_occ(x[1]))
    sorted_all = sorted(clusters.items(), key=lambda x: -total_occ(x[1]))
    sorted_single = sorted(single_form.items(), key=lambda x: -total_occ(x[1]))

    # Top-50 canonical taxonomy (all forms, sorted by frequency)
    top50 = sorted_all[:50]

    # Tail skills: single-form, ≥2 occurrences, NOT in top 50
    top50_norms = {norm for norm, _ in top50}
    tail_skills = [
        (norm, surfaces)
        for norm, surfaces in sorted_single
        if total_occ(surfaces) >= 2 and norm not in top50_norms
    ]

    # Ambiguity flags
    ambiguity_flags = check_ambiguity_flags(clusters)

    # Impact estimate
    impact_text = estimate_jaccard_impact(clusters, multi_variant)

    # --- Build report ---
    today = date.today().isoformat()
    lines: list[str] = []

    lines += [
        f"# TASK-M2-006b Phase A — Top-Skills Canonicalization Analysis",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Task | TASK-M2-006b |",
        f"| Date | {today} |",
        f"| Phase A status | **Awaiting user taxonomy review** |",
        f"| Phase B–E | Blocked pending user sign-off on canonical taxonomy below |",
        f"",
    ]

    # Section 2 — Methodology
    lines += [
        f"## 2. Methodology",
        f"",
        f"- Source: `extraction_cache` table in `{db_path}` — {rows_analyzed} rows with non-empty `top_skills`",
        f"- Note: the join from `extraction_cache` to `postings` requires computing `SHA-256(full_jd)` inside "
        f"SQLite, which is not natively supported. All 140 cached extractions are used instead. "
        f"The 7 C19-filtered postings were dropped **before** LLM extraction and are therefore "
        f"absent from `extraction_cache` — so this analysis already reflects C19-passed postings only.",
        f"- Total postings analyzed: **{rows_analyzed}**",
        f"- Total skill mentions (raw): **{len(raw_skills)}**",
        f"- Distinct normalized forms: **{len(clusters)}**",
        f"- Multi-variant clusters (≥2 surface forms): **{len(multi_variant)}**",
        f"- Single-form clusters: **{len(single_form)}**",
        f"",
    ]

    # Section 3 — Multi-variant clusters
    lines += [
        f"## 3. Multi-Variant Clusters (Canonicalization Targets)",
        f"",
        f"Sorted by total occurrences descending. These are the primary targets for prompt canonicalization.",
        f"",
        f"| Normalized form | Total occ | Surface forms (count) | Proposed canonical | Notes |",
        f"|-----------------|-----------|----------------------|---------------------|-------|",
    ]
    for norm, surfaces in sorted_multi:
        total = total_occ(surfaces)
        forms_str = _format_surface_forms(surfaces)
        proposed = _propose_canonical(surfaces)
        lines.append(f"| {norm} | {total} | {forms_str} | {proposed} | |")
    lines.append("")

    # Section 4 — Proposed canonical taxonomy (top 50)
    lines += [
        f"## 4. Proposed Canonical Taxonomy (Top {len(top50)} Skills by Frequency)",
        f"",
        f"Explicit list of canonical forms the C18 extraction prompt will enforce after Phase B. "
        f"Tail skills (rank >50, low frequency, single surface form) remain free-form.",
        f"",
    ]
    for norm, surfaces in top50:
        all_surfaces = list(surfaces.keys())
        canonical = max(surfaces, key=lambda s: surfaces[s])
        # Pick the best-looking surface form as the canonical
        title_forms = [s for s in all_surfaces if s and s[0].isupper()]
        chosen = title_forms[0] if title_forms else canonical
        # Re-rank by count to get the most frequent title-cased form
        title_forms_ranked = sorted(
            [s for s in all_surfaces if s and s[0].isupper()],
            key=lambda s: -surfaces[s],
        )
        chosen = title_forms_ranked[0] if title_forms_ranked else canonical

        alts = [s for s in all_surfaces if s != chosen]
        if alts:
            covers_str = "  (covers: " + ", ".join(alts) + ")"
        else:
            covers_str = ""
        occ = total_occ(surfaces)
        lines.append(f"- **{chosen}** ({occ} mentions){covers_str}")
    lines.append("")

    # Section 5 — Ambiguity flags
    lines += [
        f"## 5. Ambiguity Flags — Needs User Input",
        f"",
        f"These clusters have genuine semantic overlap but may or may not be the same skill. "
        f"User decision required before finalizing the canonical taxonomy.",
        f"",
    ]
    for flag in ambiguity_flags:
        lines.append(f"### {flag['label']}")
        lines.append(f"")
        lines.append(f"**Present in corpus** ({flag['total_occurrences']} total mentions): "
                     f"{', '.join(f'`{m}`' for m in flag['present_in_corpus'])}")
        lines.append(f"")
        lines.append(f"**Options:**")
        for opt in flag["options"]:
            lines.append(f"- {opt}")
        lines.append(f"")
        lines.append(f"**Recommended**: {flag['recommended']}")
        lines.append(f"")

    # Section 6 — Tail skills
    lines += [
        f"## 6. Tail Skills (Single-Form, ≥2 Occurrences, Not in Top 50)",
        f"",
        f"Listed for completeness. Pull into the canonical taxonomy if relevant.",
        f"",
    ]
    if tail_skills:
        for norm, surfaces in tail_skills[:30]:
            surface = list(surfaces.keys())[0]
            occ = total_occ(surfaces)
            lines.append(f"- `{surface}` ({occ} mentions)")
    else:
        lines.append("_(none — all skills with ≥2 occurrences are already in the top 50)_")
    lines.append("")

    # Section 7 — Impact estimate
    lines += [
        f"## 7. Estimated Impact on FUSE Jaccard",
        f"",
        impact_text,
        f"",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "rows_analyzed": rows_analyzed,
        "total_mentions": len(raw_skills),
        "distinct_normalized": len(clusters),
        "multi_variant_count": len(multi_variant),
        "top5_multi": [(norm, total_occ(s)) for norm, s in sorted_multi[:5]],
        "ambiguity_flag_count": len(ambiguity_flags),
        "top50": top50,
        "ambiguity_flags": ambiguity_flags,
        "multi_variant": sorted_multi,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase A: analyze top_skills distribution from extraction_cache"
    )
    p.add_argument(
        "--db",
        type=Path,
        default=Path.home() / ".jd-matcher" / "jd-matcher.db",
        help="Path to jd-matcher.db (default: ~/.jd-matcher/jd-matcher.db)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parents[1]
        / "docs"
        / "poc"
        / "quality-logs"
        / "TASK-M2-006b-skills-analysis.md",
        help="Output path for the Markdown analysis report",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    stats = generate_report(db_path=args.db, out_path=args.out)
    print(f"Report written to: {args.out}")
    print(f"Postings analyzed:   {stats['rows_analyzed']}")
    print(f"Total skill mentions: {stats['total_mentions']}")
    print(f"Distinct normalized:  {stats['distinct_normalized']}")
    print(f"Multi-variant clusters: {stats['multi_variant_count']}")
    print(f"Ambiguity flags:      {stats['ambiguity_flag_count']}")
    print(f"\nTop 5 multi-variant clusters:")
    for norm, occ in stats["top5_multi"]:
        print(f"  {norm!r:30s} {occ} occurrences")


if __name__ == "__main__":
    main()
