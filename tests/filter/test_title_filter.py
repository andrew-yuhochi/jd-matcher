"""
Tests for C19 — Title-Based Interest Filter.

Coverage:
  - 20 should-drop titles (each matching a deny pattern with no allow override)
  - 20 should-pass titles (legit DS/ML roles + edge cases)
  - 10 ambiguous titles (match BOTH deny AND allow — allow wins, must PASS)
  - Edge cases: empty title, non-English, HTML entities

All 53 cases must PASS at 100%. No live network calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jd_matcher.filter.title_filter import (
    FilterDecision,
    TitleFilters,
    FilterPattern,
    filter_title,
    load_filters,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).parents[2] / "config" / "title_filters.yaml"


def _filters() -> TitleFilters:
    """Load fresh filters (bypasses lru_cache by passing path explicitly)."""
    return load_filters(CONFIG_PATH)


# ---------------------------------------------------------------------------
# 20 should-DROP titles (deny pattern matches, no allow override)
# ---------------------------------------------------------------------------

DENY_CASES: list[tuple[str, str]] = [
    # (title, substring of expected matched_pattern)
    ("Director of Engineering", "Director"),
    ("VP of Engineering", "VP"),
    ("Vice President of Product", "Vice President"),
    ("Head of Engineering", "Head of"),
    ("Chief Technology Officer", "Chief"),
    ("Software Engineer", "Software (Engineer|Developer)"),
    ("Senior Software Developer", "Software (Engineer|Developer)"),
    ("Software Engineering Manager", "Software Engineering"),
    ("Backend Engineer", "Backend (Engineer|Developer)"),
    ("Backend Developer", "Backend (Engineer|Developer)"),
    ("Frontend Engineer", "Frontend (Engineer|Developer)"),
    ("Frontend Developer", "Frontend (Engineer|Developer)"),
    ("Full Stack Engineer", "Full.?Stack (Engineer|Developer)"),
    ("Full-Stack Developer", "Full.?Stack (Engineer|Developer)"),
    ("DevOps Engineer", "DevOps (Engineer|Developer|Specialist)"),
    ("QA Engineer", "QA (Engineer|Analyst|Tester|Specialist)"),
    ("Business Intelligence Analyst", "Business Intelligence"),
    ("Dashboard Developer", "Dashboard Developer"),
    ("Site Reliability Engineer", "Site Reliability Engineer"),
    ("Systems Administrator", "Systems (Administrator|Engineer)"),
]


@pytest.mark.parametrize("title,pattern_substr", DENY_CASES)
def test_should_drop(title: str, pattern_substr: str) -> None:
    decision = filter_title(title, filters=_filters())
    assert decision.action == "drop", (
        f"Expected DROP for {title!r}, got PASS "
        f"(matched_pattern={decision.matched_pattern!r})"
    )
    assert decision.matched_pattern is not None


# ---------------------------------------------------------------------------
# 20 should-PASS titles (legit DS/ML roles)
# ---------------------------------------------------------------------------

PASS_CASES: list[str] = [
    "Senior Data Scientist",
    "Staff Machine Learning Engineer",
    "Principal Data Engineer",
    "Data Analyst",
    "Machine Learning Researcher",
    "Applied Scientist",
    "NLP Engineer",
    "Computer Vision Engineer",
    "AI Research Scientist",
    "Data Platform Engineer",
    "MLOps Engineer",
    "Analytics Engineer",
    "Quantitative Analyst",
    "Research Scientist",
    "ML Infrastructure Engineer",
    "Deep Learning Engineer",
    "Data Science Manager",
    "Lead Data Scientist",
    "Senior Analytics Engineer",
    "Statistician",
]


@pytest.mark.parametrize("title", PASS_CASES)
def test_should_pass(title: str) -> None:
    decision = filter_title(title, filters=_filters())
    assert decision.action == "pass", (
        f"Expected PASS for {title!r}, got DROP "
        f"(matched_pattern={decision.matched_pattern!r}, reason={decision.reason!r})"
    )


# ---------------------------------------------------------------------------
# 10 ambiguous titles — match BOTH a deny pattern AND an allow override.
# Allow wins → must PASS.
# ---------------------------------------------------------------------------

AMBIGUOUS_CASES: list[str] = [
    # Iteration 4: leadership carve-outs removed — Director/VP/Head of/Chief all DROP now.
    # The remaining cases still match both deny and allow — allow wins → PASS.
    "Software Engineer (ML)",                     # deny: Software Engineer; allow: Software Engineer.*ML
    "Software Engineer, Machine Learning",        # deny: Software Engineer; allow: Software Engineer.*Machine Learning
    "Backend Engineer, Data Platform",            # deny: Backend Engineer; allow: Backend Engineer.*Data Platform
    "DevOps Engineer (ML Infrastructure)",        # deny: DevOps Engineer; allow: DevOps Engineer.*ML
]


@pytest.mark.parametrize("title", AMBIGUOUS_CASES)
def test_ambiguous_allow_wins(title: str) -> None:
    decision = filter_title(title, filters=_filters())
    assert decision.action == "pass", (
        f"Expected PASS (allow override) for ambiguous title {title!r}, "
        f"got DROP (matched_pattern={decision.matched_pattern!r})"
    )
    # Allow override always sets matched_pattern
    assert decision.matched_pattern is not None, (
        f"Allow-override pass should set matched_pattern for {title!r}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_title_passes() -> None:
    decision = filter_title("", filters=_filters())
    assert decision.action == "pass"
    assert decision.reason == "empty title"


def test_whitespace_only_title_passes() -> None:
    decision = filter_title("   ", filters=_filters())
    assert decision.action == "pass"
    assert decision.reason == "empty title"


def test_non_english_title_passes() -> None:
    # Chinese characters — no deny pattern should match
    decision = filter_title("数据科学家", filters=_filters())
    assert decision.action == "pass"


def test_html_entity_decoded_before_match() -> None:
    # "&amp;" decoded to "&" before matching — pattern for "Data & Analytics" style
    # This title has no deny match regardless, so it must PASS; key invariant is
    # that decoding happens and doesn't crash.
    decision = filter_title("Data &amp; Analytics Engineer", filters=_filters())
    assert decision.action == "pass"


def test_html_entity_in_denied_title() -> None:
    # "Director" with an HTML entity in surrounding text — still DROP
    decision = filter_title("Director of Engineering &amp; Operations", filters=_filters())
    assert decision.action == "drop"


# ---------------------------------------------------------------------------
# FilterDecision model shape
# ---------------------------------------------------------------------------


def test_filter_decision_pass_shape() -> None:
    decision = filter_title("Senior Data Scientist", filters=_filters())
    assert isinstance(decision, FilterDecision)
    assert decision.action == "pass"


def test_filter_decision_drop_shape() -> None:
    decision = filter_title("Director of Engineering", filters=_filters())
    assert isinstance(decision, FilterDecision)
    assert decision.action == "drop"
    assert decision.matched_pattern is not None
    assert decision.reason is not None


# ---------------------------------------------------------------------------
# Allow-first ordering invariant (unit test with synthetic config)
# ---------------------------------------------------------------------------


def test_allow_checked_before_deny() -> None:
    """If the same pattern appears in both allow and deny lists, allow wins."""
    cfg = TitleFilters(
        allow=[FilterPattern(pattern="\\bFoo\\b", kind="regex", note="allow foo")],
        deny=[FilterPattern(pattern="\\bFoo\\b", kind="regex", note="deny foo")],
    )
    decision = filter_title("Foo Engineer", filters=cfg)
    assert decision.action == "pass", "Allow-first ordering violated"


# ---------------------------------------------------------------------------
# Substring kind matching
# ---------------------------------------------------------------------------


def test_substring_kind_matches_case_insensitively() -> None:
    cfg = TitleFilters(
        allow=[],
        deny=[FilterPattern(pattern="bar baz", kind="substring", note="test")],
    )
    assert filter_title("Senior Bar Baz Manager", filters=cfg).action == "drop"
    assert filter_title("BAR BAZ lead", filters=cfg).action == "drop"
    assert filter_title("no match here", filters=cfg).action == "pass"


# ---------------------------------------------------------------------------
# Calibration regression suite (collapsed from iterations 2–5, 2026-04-27/28)
#
# Each case is non-obvious: it either overrides a deny via allow, tests an
# ambiguous title the filter must consistently handle, or locked in a rule
# change. Cases already covered by DENY_CASES / PASS_CASES / AMBIGUOUS_CASES
# above are not repeated here.
# ---------------------------------------------------------------------------

REGRESSION_CASES: list[tuple[str, str, str]] = [
    # (title, expected_action, reason)

    # --- Allow overrides for non-obvious pass cases ---
    ("AI Automation Engineer",               "pass",  "allow: AI keyword rescues Automation deny"),
    ("ML QA Engineer",                       "pass",  "allow: ML keyword rescues QA deny"),
    ("AI Research Associate",                "pass",  "allow: AI keyword rescues Research Associate deny"),
    ("Research Engineer, Machine Learning",  "pass",  "allow: ML keyword rescues Research Engineer deny"),

    # --- Director/VP/Head/Chief all drop (no carve-outs, pre_deny tier) ---
    ("Associate Director, Asset Modelling - STG Life Solutions", "drop", "pre_deny: Director"),
    ("Director, Risk Analytics",             "drop",  "pre_deny: Director"),
    ("Director of Data Science",             "drop",  "pre_deny: Director"),
    ("Director of Machine Learning",         "drop",  "pre_deny: Director"),
    ("Director, Senior AI Engineer - Remote","drop",  "pre_deny: Director (IKS Health #90)"),
    ("VP of Data",                           "drop",  "pre_deny: VP"),
    ("VP of Machine Learning",               "drop",  "pre_deny: VP"),
    ("Vice President of AI",                 "drop",  "pre_deny: Vice President"),
    ("Head of AI",                           "drop",  "pre_deny: Head of"),
    ("Head of Data Engineering",             "drop",  "pre_deny: Head of"),
    ("Chief Data Officer",                   "drop",  "pre_deny: Chief"),
    ("Chief AI Officer",                     "drop",  "pre_deny: Chief"),

    # --- Entry-level all drop (pre_deny tier) ---
    ("Junior Data Scientist",                "drop",  "pre_deny: Junior"),
    ("AI Intern",                            "drop",  "pre_deny: Intern"),
    ("AI Summer Intern",                     "drop",  "pre_deny: Intern"),
    ("Data Co-op Student",                   "drop",  "pre_deny: Co-op"),
    ("Co-op Software Developer (AI Team)",   "drop",  "pre_deny: Co-op"),
    ("Apprentice Data Engineer",             "drop",  "pre_deny: Apprentice"),
    ("ML Trainee",                           "drop",  "pre_deny: Trainee"),
    ("Graduate Data Analyst",               "drop",  "pre_deny: Graduate"),
    ("New Grad Software Engineer (ML)",      "drop",  "pre_deny: New Grad"),
    ("Fresher Data Analyst",                 "drop",  "pre_deny: Fresher (#34 in real DB)"),
    ("Entry-Level Data Scientist",           "drop",  "pre_deny: Entry Level"),
    ("Entry Level ML Engineer",              "drop",  "pre_deny: Entry Level"),

    # --- Manager is NOT pre_deny (IC still applies, pass) ---
    ("Manager, Data Science",               "pass",  "Manager is not Director — allow"),
    ("Data Science Manager, Growth",        "pass",  "Manager is not Director — allow"),
    ("Senior Manager, Machine Learning",    "pass",  "Senior Manager passes"),

    # --- 'Associate' alone passes (NOT entry-level per user policy) ---
    ("Data Associate",                      "pass",  "Associate is not entry-level"),
    ("Senior Data Scientist Associate",     "pass",  "Associate is not entry-level"),
    ("Research Associate",                  "drop",  "Research Associate deny exists separately"),

    # --- Physical/domain engineering → drop ---
    ("Mechanical Engineer - Robotics ML",   "drop",  "deny: Mechanical Engineer"),
    ("Mechanical Engineering Manager",      "drop",  "deny: Mechanical Engineer"),
    ("Civil Engineer",                      "drop",  "deny: Civil Engineer"),
    ("Chemical Engineering Specialist",     "drop",  "deny: Chemical Engineer"),
    ("Electrical Engineer",                 "drop",  "deny: Electrical Engineer"),

    # --- Finance/advisory → drop ---
    ("Investment Banking Analyst",          "drop",  "deny: Investment Banking"),
    ("Senior Investment Banking Associate", "drop",  "deny: Investment Banking"),
    ("Tax Advisor",                         "drop",  "deny: Tax"),
    ("Tax Manager",                         "drop",  "deny: Tax"),
    ("Tax Consultant - Financial Services", "drop",  "deny: Tax"),

    # --- Iteration 5: domain-qualified drops ---
    ("Startup Event Representative (Tech / Web Summit Vancouver)", "drop", "deny: event rep"),
    ("Email Operations Specialist (Klaviyo/AI/Figma/Claude)",      "drop", "deny: email ops"),
    ("Creative Lead, Growth & Storytelling",                       "drop", "deny: creative"),
    ("Partner Alliance Analyst",                                   "drop", "deny: alliance"),
    ("Finance & Strategy Manager, Hopper/HTS (100% Remote - Canada)", "drop", "deny: finance"),
    ("Finance and Strategy Manager",                               "drop", "deny: finance (and variant)"),
    ("AI Trainer - Freelance Data Annotator",                      "drop", "deny: AI trainer/annotator"),
    ("Ai Trainer / Ai Data Trainer - Remote",                      "drop", "deny: AI trainer"),
    ("French Canada - AI Data Contributor",                        "drop", "deny: data contributor"),
    ("R&D Scientist, Novel Ingredients",                           "drop", "deny: pharma R&D"),
    ("Process Development Scientist, GMP Media",                   "drop", "deny: pharma process dev"),
    ("Scientist II, Analytical Development",                       "drop", "deny: analytical dev (not the II)"),
    ("Data Scientist, Early Career (Canada)",                      "drop", "deny: early career"),
    ("Machine Learning Engineer - Early Career (Canada)",          "drop", "deny: early career"),

    # --- Level suffix I/II/III not a drop signal (policy: ambiguous) ---
    ("Associate Data Scientist - User Fraud", "pass", "Associate not entry-level"),
    ("Programmer Analyst I",                 "pass",  "I suffix not a drop signal"),
    ("Intermediate II Software Developer - Artificial Intelligence", "pass", "II suffix not a drop; AI allow fires"),
    ("Senior Data Analyst II",              "pass",  "II suffix not a drop"),
    ("Data Scientist III",                  "pass",  "III suffix not a drop"),

    # --- Domain-specialist roles that pass (let LLM decide or DS-adjacent) ---
    ("Research And Development Specialist", "pass",  "too generic — let LLM see JD"),
    ("Senior Web Developer",               "pass",  "might be ML platform — let LLM decide"),
    ("Lead Platform Engineer",             "pass",  "might be ML platform"),
    ("Quantitative Researcher, Fixed Income", "pass", "quant finance kept"),
    ("Bioinformatics Scientist (Remote)",  "pass",  "computational biology = DS-adjacent"),

    # --- Regression: deny patterns don't accidentally swallow DS-adjacent roles ---
    ("Software Engineer (ML)",             "pass",  "allow: ML keyword rescues SWE deny"),
    ("AI Engineer",                        "pass",  "allow: AI keyword passes"),
    ("Data Scientist - Tax Strategy",      "pass",  "legit DS role with Tax word"),
    ("Machine Learning Engineer",          "pass",  "core DS/ML role"),

    # --- Misc deny patterns ---
    ("Flutter Developer",                  "drop",  "deny: Flutter Developer"),
    ("Environmental Scientist",            "drop",  "deny: Environmental Scientist"),
    ("Water Resources Engineer/Scientist/Modeller", "drop", "deny: Water Resources"),
    ("Clinical Research Assistant",        "drop",  "deny: Clinical Research"),
    ("Senior Manager, Trial Operations",   "drop",  "deny: Trial Operations"),
    ("Personalized Internet Assessor - Persian speakers in Canada", "drop", "deny: Assessor"),
    ("Senior, Economic Advisory (Vancouver)", "drop", "deny: Economic Advisory"),
]


@pytest.mark.parametrize("title,expected_action,reason", REGRESSION_CASES)
def test_calibration_regression(title: str, expected_action: str, reason: str) -> None:
    """Collapsed calibration regression suite (iterations 2–5).

    Each case is non-obvious and not already covered by DENY_CASES / PASS_CASES /
    AMBIGUOUS_CASES. The 'reason' parameter documents the policy intent for
    future reviewers.
    """
    from jd_matcher.filter.title_filter import filter_title
    decision = filter_title(title)
    assert decision.action == expected_action, (
        f"{title!r} [{reason}]: expected {expected_action}, got {decision.action} "
        f"(matched {decision.matched_pattern!r})"
    )


# ---------------------------------------------------------------------------
# Iteration 7 calibration cases (2026-04-27) — company-based filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,company,expected_action", [
    # Staffing firms / job-ad platforms — company match triggers deny_company drop.
    # Title alone would not drop these (all are plausible DS/ML titles).
    ("Bioinformatics Scientist (Remote)",        "Jobs Ai",                     "drop"),
    ("Senior Machine Learning Engineer",          "Jobs AI",                     "drop"),  # case variant
    ("Data Scientist",                            "Joveo",                       "drop"),
    ("AI Engineer",                               "Crossing Hurdles",            "drop"),
    ("Data Operations Manager",                   "Crossing Hurdles",            "drop"),
    ("Data Scientist",                            "Alquemy Search & Consulting", "drop"),
    ("AI/ML Engineer",                            "Alquemy Search & Consulting", "drop"),  # variant
    ("AI/ML Engineer",                            "YO HR Consultancy",           "drop"),
    # Critical regression: legitimate companies must KEEP
    ("Senior Data Scientist",                     "Stripe",                      "pass"),
    ("Senior Machine Learning Engineer",          "Cohere",                      "pass"),
    ("Data Scientist",                            "Dropbox",                     "pass"),
    ("AI Engineer",                               "Lumenalta",                   "pass"),
    # Backward compat: company=None — deny_company tier skipped entirely
    ("Senior Data Scientist",                     None,                          "pass"),
    ("Director of Engineering",                   None,                          "drop"),  # via pre_deny
    ("AI Intern",                                 None,                          "drop"),  # via pre_deny
    # Edge: empty string treated as falsy — deny_company tier skipped
    ("Senior Data Scientist",                     "",                            "pass"),
])
def test_iteration_7_company_filtering(title: str, company: str | None, expected_action: str) -> None:
    """Iteration 7: company-based filtering via deny_company tier."""
    from jd_matcher.filter.title_filter import filter_title
    decision = filter_title(title, company=company)
    assert decision.action == expected_action, (
        f"title={title!r} company={company!r}: expected {expected_action}, "
        f"got {decision.action} (matched {decision.matched_pattern!r})"
    )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def test_load_filters_returns_title_filters() -> None:
    filters = load_filters(CONFIG_PATH)
    assert isinstance(filters, TitleFilters)
    assert len(filters.deny) > 0
    assert len(filters.allow) > 0


def test_filters_have_required_fields() -> None:
    filters = load_filters(CONFIG_PATH)
    for p in filters.deny + filters.allow:
        assert p.kind in ("regex", "substring")
        assert isinstance(p.pattern, str)
        assert len(p.pattern) > 0
