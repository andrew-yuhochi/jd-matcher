"""
Skills tiering engine (TASK-M2-016).

Classifies card skills into 4 categories (ds_ml, languages, platforms, other)
and determines match state against the user's core_skills from user_profile.yaml.
Ordering: matching skills first (ds_ml → languages → platforms → other),
non-matching skills appended in their original order.

Public API:
    load_skill_categories(config_path) -> SkillCategoryMap
    load_user_profile(config_path)     -> UserProfile
    classify_and_sort_skills(top_skills, user_profile, skill_categories)
        -> tuple[list[ClassifiedSkill], int, int]
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Config paths relative to project root (this file is src/jd_matcher/skills/__init__.py,
# so parents[3] = project root).
_PROJECT_ROOT = Path(__file__).parents[3]
_DEFAULT_CATEGORIES_PATH = _PROJECT_ROOT / "config" / "skill_categories.yaml"
_DEFAULT_PROFILE_PATH = _PROJECT_ROOT / "config" / "user_profile.yaml"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ClassifiedSkill(BaseModel):
    skill: str       # original case from card
    category: str    # one of: ds_ml, languages, platforms, other
    css_class: str   # e.g., "skill-chip-ds"
    is_match: bool   # in user's core_skills


class CategorySpec(BaseModel):
    color: str
    css_class: str
    skills: list[str]


class SkillCategoryMap(BaseModel):
    categories: dict[str, CategorySpec]
    priority_order: list[str]
    # alias_map: alias_lower → canonical_lower (built once at load time)
    alias_map: dict[str, str]


class UserProfile(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    core_skills: list[str]
    # core_skills_normalized: canonical-lower set for O(1) match lookups
    core_skills_normalized: set[str]


# ---------------------------------------------------------------------------
# Alias normalization
# ---------------------------------------------------------------------------


def _build_alias_map(raw_aliases: dict[str, list[str]]) -> dict[str, str]:
    """Build alias_lower → canonical_lower forward map from the YAML aliases block.

    Each canonical key maps to a list of aliases. We want:
      alias_lower → canonical_lower
    so that normalize_skill("GenAI") returns "generative ai" (same as the canonical).
    """
    alias_map: dict[str, str] = {}
    for canonical, aliases in raw_aliases.items():
        canonical_lower = canonical.lower()
        # The canonical itself normalizes to itself
        alias_map[canonical_lower] = canonical_lower
        for alias in aliases:
            alias_map[alias.lower()] = canonical_lower
    return alias_map


def _normalize_skill(skill: str, alias_map: dict[str, str]) -> str:
    """Return the canonical-lower form of a skill, applying alias resolution."""
    lower = skill.lower()
    return alias_map.get(lower, lower)


# ---------------------------------------------------------------------------
# Config loaders — cached at module level (load-once-at-startup)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_skill_categories(
    config_path: Path = _DEFAULT_CATEGORIES_PATH,
) -> SkillCategoryMap:
    """Load and cache skill_categories.yaml. Falls back to empty map on missing file."""
    if not config_path.exists():
        logger.warning("skill_categories.yaml not found at %s — falling back to empty map", config_path)
        return SkillCategoryMap(
            categories={},
            priority_order=[],
            alias_map={},
        )
    try:
        raw = yaml.safe_load(config_path.read_text())
        raw_categories: dict[str, dict] = raw.get("categories", {})
        priority_order: list[str] = raw.get("priority_order", [])
        raw_aliases: dict[str, list[str]] = raw.get("aliases", {})

        categories: dict[str, CategorySpec] = {}
        for cat_key, cat_data in raw_categories.items():
            categories[cat_key] = CategorySpec(
                color=cat_data.get("color", "gray"),
                css_class=cat_data.get("css_class", f"skill-chip-{cat_key}"),
                skills=cat_data.get("skills", []),
            )

        alias_map = _build_alias_map(raw_aliases)

        # Build category skill lookup: skill_lower → category_key
        # (built into the SkillCategoryMap implicitly via _get_category_for_skill)
        return SkillCategoryMap(
            categories=categories,
            priority_order=priority_order,
            alias_map=alias_map,
        )
    except Exception:
        logger.exception("Failed to load skill_categories.yaml — falling back to empty map")
        return SkillCategoryMap(categories={}, priority_order=[], alias_map={})


@lru_cache(maxsize=1)
def load_user_profile(
    config_path: Path = _DEFAULT_PROFILE_PATH,
) -> UserProfile:
    """Load and cache user_profile.yaml. Falls back to empty profile on missing file."""
    if not config_path.exists():
        logger.warning("user_profile.yaml not found at %s — falling back to empty profile", config_path)
        return UserProfile(core_skills=[], core_skills_normalized=set())
    try:
        raw = yaml.safe_load(config_path.read_text())
        core_skills: list[str] = raw.get("core_skills", [])
        return UserProfile(core_skills=core_skills, core_skills_normalized=set())
    except Exception:
        logger.exception("Failed to load user_profile.yaml — falling back to empty profile")
        return UserProfile(core_skills=[], core_skills_normalized=set())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_core_skills_normalized(
    profile: UserProfile,
    alias_map: dict[str, str],
) -> set[str]:
    """Build the normalized set of user core skills for O(1) match checking."""
    return {_normalize_skill(s, alias_map) for s in profile.core_skills}


def _get_category_for_skill(
    skill_normalized: str,
    skill_map: SkillCategoryMap,
) -> tuple[str, str]:
    """Return (category_key, css_class) for the given normalized skill.

    Searches ds_ml, languages, platforms in priority order. Falls back to other.
    """
    for cat_key in ("ds_ml", "languages", "platforms"):
        spec = skill_map.categories.get(cat_key)
        if spec is None:
            continue
        for cat_skill in spec.skills:
            if _normalize_skill(cat_skill, skill_map.alias_map) == skill_normalized:
                return cat_key, spec.css_class

    other_spec = skill_map.categories.get("other")
    other_css = other_spec.css_class if other_spec else "skill-chip-other"
    return "other", other_css


# ---------------------------------------------------------------------------
# Public classification function
# ---------------------------------------------------------------------------


def classify_and_sort_skills(
    top_skills: list[str],
    user_profile: UserProfile,
    skill_categories: SkillCategoryMap,
) -> tuple[list[ClassifiedSkill], int, int]:
    """Classify and sort skills for display on canonical cards.

    Ordering:
      1. Matching skills first, grouped by category and sorted within category
         by priority_order (ds_ml → languages → platforms → other).
         Within a category group, original incoming order is preserved.
      2. Non-matching skills appended in original incoming order.
    Cap of 10 is applied LAST, after sorting, to preserve match priority.

    Returns (ordered_skills[:10], match_count, total_count).
    match_count and total_count are computed against ALL skills (before cap).
    """
    if not top_skills:
        return [], 0, 0

    core_normalized = _build_core_skills_normalized(user_profile, skill_categories.alias_map)

    classified: list[ClassifiedSkill] = []
    for skill in top_skills:
        skill_norm = _normalize_skill(skill, skill_categories.alias_map)
        is_match = skill_norm in core_normalized
        category, css_class = _get_category_for_skill(skill_norm, skill_categories)
        classified.append(ClassifiedSkill(
            skill=skill,
            category=category,
            css_class=css_class,
            is_match=is_match,
        ))

    total_count = len(classified)
    match_count = sum(1 for cs in classified if cs.is_match)

    # Build priority index for ordering: category → sort_position (lower = first)
    priority_index: dict[str, int] = {
        cat: i
        for i, cat in enumerate(skill_categories.priority_order or ["ds_ml", "languages", "platforms", "other"])
    }
    _fallback_priority = len(priority_index)

    def _sort_key(item: tuple[int, ClassifiedSkill]) -> tuple[int, int, int]:
        original_idx, cs = item
        match_first = 0 if cs.is_match else 1
        cat_priority = priority_index.get(cs.category, _fallback_priority)
        return (match_first, cat_priority, original_idx)

    sorted_classified = [
        cs
        for _idx, cs in sorted(enumerate(classified), key=_sort_key)
    ]

    return sorted_classified[:10], match_count, total_count
