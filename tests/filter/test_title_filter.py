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
# Iteration 2 calibration cases (2026-04-27)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,expected_action", [
    # Fixed false positive — #85 AI Automation Engineer (allow override fires before Automation deny)
    ("AI Automation Engineer", "pass"),
    ("ML QA Engineer", "pass"),
    # Iteration 4: Director carve-outs removed — these now DROP (no allow overrides)
    ("Associate Director, Asset Modelling - STG Life Solutions", "drop"),
    ("Director, Risk Analytics", "drop"),
    # New deny patterns
    ("Flutter Developer", "drop"),
    ("Environmental Scientist", "drop"),
    ("Water Resources Engineer/Scientist/Modeller", "drop"),
    ("Clinical Research Assistant", "drop"),
    ("Senior Manager, Trial Operations", "drop"),
    ("Personalized Internet Assessor - Persian speakers in Canada", "drop"),
    ("Senior, Economic Advisory (Vancouver)", "drop"),
    # Research Associate deny + AI/ML allow overrides
    ("Research Associate", "drop"),
    ("AI Research Associate", "pass"),
    ("Research Engineer, Machine Learning", "pass"),
])
def test_iteration_2_calibration(title: str, expected_action: str) -> None:
    from jd_matcher.filter.title_filter import filter_title
    decision = filter_title(title)
    assert decision.action == expected_action, (
        f"{title!r}: expected {expected_action}, got {decision.action} "
        f"(matched {decision.matched_pattern!r})"
    )


# ---------------------------------------------------------------------------
# Iteration 3 calibration cases (2026-04-27)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,expected_action", [
    # User-flagged false negatives in iteration 3 — must now drop
    ("Mechanical Engineer - Robotics ML",         "drop"),
    ("Mechanical Engineering Manager",            "drop"),
    ("Civil Engineer",                            "drop"),
    ("Chemical Engineering Specialist",           "drop"),
    ("Electrical Engineer",                       "drop"),
    ("Investment Banking Analyst",                "drop"),
    ("Senior Investment Banking Associate",       "drop"),
    ("Tax Advisor",                               "drop"),
    ("Tax Manager",                               "drop"),
    ("Tax Consultant - Financial Services",       "drop"),
    # And confirm the new patterns don't accidentally swallow DS adjacent roles
    ("Software Engineer (ML)",                    "pass"),  # regression — was passing, still must
    ("AI Engineer",                               "pass"),  # regression
    ("Data Scientist - Tax Strategy",             "pass"),  # legit DS role with "Tax" word
    ("Machine Learning Engineer",                 "pass"),  # regression
])
def test_iteration_3_calibration(title: str, expected_action: str) -> None:
    from jd_matcher.filter.title_filter import filter_title
    decision = filter_title(title)
    assert decision.action == expected_action, (
        f"{title!r}: expected {expected_action}, got {decision.action} "
        f"(matched {decision.matched_pattern!r})"
    )


# ---------------------------------------------------------------------------
# Iteration 4 calibration cases (2026-04-27)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,expected_action", [
    # All leadership now drops, no carve-outs
    ("Director of Data Science",                  "drop"),
    ("Director of Machine Learning",              "drop"),
    ("Associate Director, Asset Modelling",       "drop"),
    ("Director, Risk Analytics",                  "drop"),
    ("Director, Senior AI Engineer - Remote",     "drop"),  # IKS Health #90
    ("VP of Data",                                "drop"),
    ("VP of Machine Learning",                    "drop"),
    ("Vice President of AI",                      "drop"),
    ("Head of AI",                                "drop"),
    ("Head of Data Engineering",                  "drop"),
    ("Chief Data Officer",                        "drop"),
    ("Chief AI Officer",                          "drop"),
    # All entry-level drops
    ("Junior Data Scientist",                     "drop"),
    ("AI Intern",                                 "drop"),
    ("AI Summer Intern",                          "drop"),
    ("Data Co-op Student",                        "drop"),
    ("Co-op Software Developer (AI Team)",        "drop"),
    ("Apprentice Data Engineer",                  "drop"),
    ("ML Trainee",                                "drop"),
    ("Graduate Data Analyst",                     "drop"),
    ("New Grad Software Engineer (ML)",           "drop"),
    ("Fresher Data Analyst",                      "drop"),  # #34 in real DB
    ("Entry-Level Data Scientist",                "drop"),
    ("Entry Level ML Engineer",                   "drop"),
    # Senior IC roles still pass — these are the user's target
    ("Senior Data Scientist",                     "pass"),
    ("Staff Machine Learning Engineer",           "pass"),
    ("Lead Data Scientist",                       "pass"),
    ("Principal AI Engineer",                     "pass"),
    ("Manager, Data Science",                     "pass"),  # Manager is NOT Director — allow
    ("Data Science Manager, Growth",              "pass"),
    ("Senior Manager, Machine Learning",          "pass"),
    # 'Associate' alone still passes (NOT entry-level per user)
    ("Data Associate",                            "pass"),
    ("Senior Data Scientist Associate",           "pass"),
    ("Research Associate",                        "drop"),  # Research Associate deny exists separately — sanity check unchanged
    ("AI Research Associate",                     "pass"),  # allow override on AI/ML + Research — sanity check unchanged
])
def test_iteration_4_calibration(title: str, expected_action: str) -> None:
    from jd_matcher.filter.title_filter import filter_title
    decision = filter_title(title)
    assert decision.action == expected_action, (
        f"{title!r}: expected {expected_action}, got {decision.action} "
        f"(matched {decision.matched_pattern!r})"
    )


# ---------------------------------------------------------------------------
# Iteration 5 calibration cases (2026-04-28)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("title,expected_action", [
    # Iteration 5 — new drops (15 specific titles flagged from 156-posting review)
    ("Startup Event Representative (Tech / Web Summit Vancouver)", "drop"),
    ("Email Operations Specialist (Klaviyo/AI/Figma/Claude)", "drop"),
    ("Creative Lead, Growth & Storytelling", "drop"),
    ("Partner Alliance Analyst", "drop"),
    ("Finance & Strategy Manager, Hopper/HTS (100% Remote - Canada)", "drop"),
    ("Finance and Strategy Manager", "drop"),  # variant: "and" not "&"
    ("AI Trainer - Freelance Data Annotator", "drop"),
    ("Ai Trainer / Ai Data Trainer - Remote", "drop"),
    ("French Canada - AI Data Contributor", "drop"),
    ("R&D Scientist, Novel Ingredients", "drop"),
    ("Process Development Scientist, GMP Media", "drop"),
    ("Scientist II, Analytical Development", "drop"),  # drops on Analytical Development, NOT the "II"
    ("Data Scientist, Early Career (Canada)", "drop"),
    ("Machine Learning Engineer - Early Career (Canada)", "drop"),
    # Critical regression checks — KEEP per user explicit direction
    ("Associate Data Scientist - User Fraud", "pass"),  # Associate is not entry-level
    ("Programmer Analyst I", "pass"),                    # "I" suffix NOT a drop signal
    ("Intermediate II Software Developer - Artificial Intelligence", "pass"),  # "II" suffix NOT a drop signal
    # Note: "Software Engineer II" / "Software Engineer III" still DROP on the
    # base \bSoftware Engineer\b deny (no ML context); II/III don't change that.
    # User's policy is "don't ADD deny patterns for I/II/III", not "always keep
    # titles with those suffixes". Base denies still apply when no ML keyword
    # is present. Not tested here — covered by the existing base SWE deny tests.
    ("Senior Data Analyst II", "pass"),                  # same: II is ambiguous
    ("Data Scientist III", "pass"),                      # same: III is ambiguous
    ("Research And Development Specialist", "pass"),     # too generic — let LLM see JD
    ("Senior Web Developer", "pass"),                    # might be ML platform, let LLM decide
    ("Lead Platform Engineer", "pass"),                  # might be ML platform
    ("Quantitative Researcher, Fixed Income", "pass"),   # quant finance kept
    ("Bioinformatics Scientist (Remote)", "pass"),       # computational biology = DS-adjacent
])
def test_iteration_5_calibration(title: str, expected_action: str) -> None:
    """Iteration 5 calibration: 14 new drops + 11 critical regression checks.

    Per user direction 2026-04-28:
    - Drop on domain qualifiers (Event/Email/Creative/Finance/Annotator/Pharma/Early Career)
    - DO NOT drop on level suffixes (I/II/III) — those are ambiguous between
      junior and senior at different companies. Use explicit "Junior"/"Intern"/
      "Early Career" or look at JD content for level detection.
    """
    from jd_matcher.filter.title_filter import filter_title
    decision = filter_title(title)
    assert decision.action == expected_action, (
        f"{title!r}: expected {expected_action}, got {decision.action} "
        f"(matched {decision.matched_pattern!r})"
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
