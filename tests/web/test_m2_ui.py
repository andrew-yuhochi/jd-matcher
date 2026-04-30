"""
DOM structural tests for M2 Web UI updates (TASK-M2-011).

Covers:
  AC #1 — Multi-source rendering: Sources row with per-source apply links
  AC #2 — Reposted badge renders for canonicals with merge_kind='repost'
  AC #3 — Apply/dismiss suppress canonical from main (apply-one-suppress-all)
  AC #4 — canonical_id is the card DOM id; data-canonical-id attr present
  AC #5 — Source-count badge appears when canonical has >1 source
  AC #6 — O shortcut cheatsheet entry present in base.html
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from jd_matcher.db.init_db import init_db
from jd_matcher.web.app import app

TS = "2026-04-25T10:00:00+00:00"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_canonical(
    conn: sqlite3.Connection,
    title: str,
    *,
    hydration_status: str = "complete",
    full_jd: str = "",
) -> tuple[int, int]:
    """Insert posting + canonical + link. Returns (posting_id, canonical_id)."""
    cur_p = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen, full_jd)
        VALUES ('default', ?, ?, ?, ?, ?)
        """,
        (title, hydration_status, TS, TS, full_jd),
    )
    pid = cur_p.lastrowid

    cur_c = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_seniority,
             canonical_location, top_skills, role_summary, full_jd,
             full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', ?, 'TestCo', 'Mid', 'Vancouver, BC',
                '[]', 'A test role.', ?, '{}', ?, ?, '[]')
        """,
        (title, full_jd, TS, TS),
    )
    cid = cur_c.lastrowid

    conn.execute(
        """
        INSERT INTO posting_canonical_links
            (user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at)
        VALUES ('default', ?, ?, 1.0, 'new_canonical', ?)
        """,
        (pid, cid, TS),
    )
    return pid, cid


def _add_repost_posting(
    conn: sqlite3.Connection,
    canonical_id: int,
    title: str,
    source: str = "linkedin",
    source_url: str = "https://linkedin.com/jobs/view/99999",
) -> int:
    """Add a second posting linked to an existing canonical as a repost."""
    cur_p = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen)
        VALUES ('default', ?, 'complete', ?, ?)
        """,
        (title, TS, TS),
    )
    pid = cur_p.lastrowid

    conn.execute(
        """
        INSERT OR IGNORE INTO posting_canonical_links
            (user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at)
        VALUES ('default', ?, ?, 0.95, 'repost', ?)
        """,
        (pid, canonical_id, TS),
    )

    conn.execute(
        """
        INSERT INTO posting_sources
            (posting_id, user_id, source, source_url, source_first_seen)
        VALUES (?, 'default', ?, ?, ?)
        """,
        (pid, source, source_url, TS),
    )
    return pid


def _add_source(
    conn: sqlite3.Connection,
    posting_id: int,
    source: str,
    source_url: str,
) -> None:
    """Add a posting_sources row for a posting."""
    conn.execute(
        """
        INSERT INTO posting_sources
            (posting_id, user_id, source, source_url, source_first_seen)
        VALUES (?, 'default', ?, ?, ?)
        """,
        (posting_id, source, source_url, TS),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Generator[Path, None, None]:
    db_path = tmp_path / "m2_ui.db"
    init_db(db_path)
    old = os.environ.get("JD_MATCHER_DB_PATH")
    os.environ["JD_MATCHER_DB_PATH"] = str(db_path)
    try:
        yield db_path
    finally:
        if old is None:
            os.environ.pop("JD_MATCHER_DB_PATH", None)
        else:
            os.environ["JD_MATCHER_DB_PATH"] = old


@pytest.fixture()
def client(db: Path) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# AC #4 — Canonical-id as card DOM id + data-canonical-id attr
# ---------------------------------------------------------------------------


def test_canonical_card_id_uses_canonical_id(client: TestClient, db: Path) -> None:
    """Main tab card element id must be card-{canonical_id}, not card-{posting_id}."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Canonical ID Test")
    conn.commit()
    conn.close()

    html = client.get("/").text
    assert f'id="card-{cid}"' in html, f"card-{cid} (canonical) missing from main tab"
    assert f'data-canonical-id="{cid}"' in html, "data-canonical-id attr missing"


def test_canonical_card_has_data_posting_id(client: TestClient, db: Path) -> None:
    """Card must also carry data-posting-id for POST endpoint compatibility."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, _cid = _seed_canonical(conn, "Data Posting ID Test")
    conn.commit()
    conn.close()

    html = client.get("/").text
    assert f'data-posting-id="{pid}"' in html, "data-posting-id missing from canonical card"


# ---------------------------------------------------------------------------
# AC #1 — Multi-source rendering
# ---------------------------------------------------------------------------


def test_single_source_card_shows_apply_link(client: TestClient, db: Path) -> None:
    """A canonical with one source renders an apply link."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Single Source Job")
    _add_source(conn, pid, "linkedin", "https://linkedin.com/jobs/view/11111")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing from main tab"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "Sources:" in fragment, "Sources: label missing from card"
    assert "Apply on LinkedIn" in fragment, "Apply on LinkedIn link missing"
    assert "card-apply-link" in fragment, "card-apply-link class missing"


def test_multi_source_card_shows_all_apply_links(client: TestClient, db: Path) -> None:
    """A canonical with two sources renders two apply links in Sources row."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    # Seed two postings linked to the same canonical (one LinkedIn, one Indeed)
    pid1, cid = _seed_canonical(conn, "Multi Source Job")
    _add_source(conn, pid1, "linkedin", "https://linkedin.com/jobs/view/22222")

    # Add Indeed posting as a second source (content dedup)
    cur_p2 = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'Multi Source Job (Indeed)', 'complete', ?, ?)",
        (TS, TS),
    )
    pid2 = cur_p2.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 0.97, 'content_dedup', ?)",
        (pid2, cid, TS),
    )
    _add_source(conn, pid2, "indeed", "https://indeed.com/viewjob?jk=abc123")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "Apply on LinkedIn" in fragment, "LinkedIn apply link missing from multi-source card"
    assert "Apply on Indeed" in fragment, "Indeed apply link missing from multi-source card"


def test_multi_source_linkedin_before_indeed(client: TestClient, db: Path) -> None:
    """LinkedIn apply link must appear before Indeed in DOM order (source precedence)."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    pid1, cid = _seed_canonical(conn, "Precedence Test")
    _add_source(conn, pid1, "indeed", "https://indeed.com/viewjob?jk=first")

    cur_p2 = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'Precedence Test 2', 'complete', ?, ?)",
        (TS, TS),
    )
    pid2 = cur_p2.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 0.97, 'content_dedup', ?)",
        (pid2, cid, TS),
    )
    _add_source(conn, pid2, "linkedin", "https://linkedin.com/jobs/view/33333")
    conn.commit()
    conn.close()

    html = client.get("/").text
    li_pos = html.find("Apply on LinkedIn")
    in_pos = html.find("Apply on Indeed")
    assert li_pos != -1, "LinkedIn apply link missing"
    assert in_pos != -1, "Indeed apply link missing"
    assert li_pos < in_pos, "LinkedIn link must appear before Indeed link in DOM"


# ---------------------------------------------------------------------------
# AC #5 — Source-count badge
# ---------------------------------------------------------------------------


def test_source_count_badge_shown_for_multi_source(client: TestClient, db: Path) -> None:
    """Cards with >1 source must show a badge-source-count element."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")

    pid1, cid = _seed_canonical(conn, "Source Count Badge Test")
    _add_source(conn, pid1, "linkedin", "https://linkedin.com/jobs/view/44444")

    cur_p2 = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'Source Count Badge Test 2', 'complete', ?, ?)",
        (TS, TS),
    )
    pid2 = cur_p2.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 0.97, 'content_dedup', ?)",
        (pid2, cid, TS),
    )
    _add_source(conn, pid2, "indeed", "https://indeed.com/viewjob?jk=def456")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "badge-source-count" in fragment, (
        "badge-source-count missing — multi-source card must show source count badge"
    )
    assert "2 variants" in fragment, "Source count '2 variants' text missing"


def test_source_count_badge_absent_for_single_source(client: TestClient, db: Path) -> None:
    """Single-source cards must NOT show the source-count badge."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Single Source No Badge")
    _add_source(conn, pid, "linkedin", "https://linkedin.com/jobs/view/55555")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "badge-source-count" not in fragment, (
        "badge-source-count must NOT appear on single-source cards"
    )


# ---------------------------------------------------------------------------
# AC #2 — Reposted badge
# ---------------------------------------------------------------------------


def test_reposted_badge_renders_for_repost_canonical(client: TestClient, db: Path) -> None:
    """Canonicals with any posting_canonical_links.merge_kind='repost' show Reposted badge."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical(conn, "Reposted Job")
    _add_repost_posting(conn, cid, "Reposted Job v2")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing from main tab"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "badge-reposted" in fragment, "badge-reposted class missing for repost canonical"
    assert "Reposted" in fragment, "Reposted text missing from badge"


def test_reposted_badge_absent_for_non_repost(client: TestClient, db: Path) -> None:
    """New canonical (merge_kind='new_canonical') must NOT show Reposted badge."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical(conn, "Non-Repost Job")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "badge-reposted" not in fragment, (
        "badge-reposted must not appear for non-repost canonicals"
    )


def test_reposted_badge_has_tooltip(client: TestClient, db: Path) -> None:
    """Reposted badge must have a title= tooltip attribute."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical(conn, "Reposted Tooltip Test")
    _add_repost_posting(conn, cid, "Reposted Tooltip Test v2")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    badge_start = fragment.find("badge-reposted")
    assert badge_start != -1
    # The badge span should have a title= attribute
    badge_fragment = fragment[badge_start : badge_start + 300]
    assert "title=" in badge_fragment, "Reposted badge is missing title= tooltip"
    assert "reposted" in badge_fragment.lower(), "Reposted tooltip text missing context"


# ---------------------------------------------------------------------------
# AC #3 — Apply-one-suppress-all invariant (canonical-level state)
# ---------------------------------------------------------------------------


def test_applying_one_posting_suppresses_whole_canonical(
    client: TestClient, db: Path
) -> None:
    """Applying any posting linked to a canonical removes the canonical from main view."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Suppress Test")
    conn.commit()
    conn.close()

    resp_before = client.get("/")
    assert f'id="card-{cid}"' in resp_before.text

    # Apply via posting_id (POST endpoint still takes posting_id)
    resp_apply = client.post(f"/postings/{pid}/apply")
    assert resp_apply.status_code == 200

    resp_after = client.get("/")
    assert f'id="card-{cid}"' not in resp_after.text, (
        "Canonical card still visible after applying one of its postings — "
        "apply-one-suppress-all invariant violated"
    )


def test_dismissing_one_posting_suppresses_whole_canonical(
    client: TestClient, db: Path
) -> None:
    """Dismissing any posting linked to a canonical removes the canonical from main view."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Dismiss Suppress Test")
    conn.commit()
    conn.close()

    resp_before = client.get("/")
    assert f'id="card-{cid}"' in resp_before.text

    resp_dismiss = client.post(f"/postings/{pid}/dismiss")
    assert resp_dismiss.status_code == 200

    resp_after = client.get("/")
    assert f'id="card-{cid}"' not in resp_after.text, (
        "Canonical card still visible after dismissing one of its postings — "
        "apply-one-suppress-all invariant violated"
    )


# ---------------------------------------------------------------------------
# AC #6 — O shortcut in cheatsheet
# ---------------------------------------------------------------------------


def test_cheatsheet_has_shift_o_shortcut(client: TestClient, db: Path) -> None:
    """The cheatsheet modal must list the O shortcut for opening all apply URLs."""
    html = client.get("/").text
    assert "Open all apply URLs" in html, (
        "O shortcut (open all URLs) missing from cheatsheet modal"
    )


def test_cheatsheet_has_o_shortcut_updated(client: TestClient, db: Path) -> None:
    """The o shortcut description must reference 'first apply URL'."""
    html = client.get("/").text
    assert "first apply URL" in html, (
        "o shortcut description must reference 'first apply URL' per M2 update"
    )


# ---------------------------------------------------------------------------
# CSS — .badge-reposted defined in styles.css
# ---------------------------------------------------------------------------


def test_badge_reposted_css_defined() -> None:
    """styles.css must contain the .badge-reposted rule."""
    css_path = (
        Path(__file__).parents[2]
        / "src" / "jd_matcher" / "web" / "static" / "css" / "styles.css"
    )
    css = css_path.read_text()
    assert ".badge-reposted" in css, ".badge-reposted CSS rule missing from styles.css"


def test_badge_source_count_css_defined() -> None:
    """styles.css must contain the .badge-source-count rule."""
    css_path = (
        Path(__file__).parents[2]
        / "src" / "jd_matcher" / "web" / "static" / "css" / "styles.css"
    )
    css = css_path.read_text()
    assert ".badge-source-count" in css, ".badge-source-count CSS rule missing from styles.css"


# ---------------------------------------------------------------------------
# Hydration-warning no-filter invariant extends to canonicals (M2 extension)
# ---------------------------------------------------------------------------


def test_failed_hydration_canonical_still_shows_warning(
    client: TestClient, db: Path
) -> None:
    """Canonical whose only linked posting has hydration_status='failed' renders
    with the JD incomplete warning — no-filter invariant extends to canonicals."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical(conn, "All-Failed Canonical", hydration_status="failed")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, "Failed-hydration canonical absent from main tab"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert 'class="warning"' in fragment, (
        "Failed-hydration canonical missing .warning element — no-filter invariant violated"
    )


# ---------------------------------------------------------------------------
# Follow-up fix (2026-04-29): source dedup by display_name + canonical_id chip
# ---------------------------------------------------------------------------


def test_email_and_hydrator_for_same_posting_collapse_to_one_button(
    client: TestClient, db: Path
) -> None:
    """When a posting has both linkedin_email and linkedin_hydrator rows in
    posting_sources, only ONE Apply on LinkedIn button must render, using
    the hydrator (clean) URL — not the tracking-laden email URL."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Email+Hydrator Collapse Test")
    # Two rows for the same posting_id: email (tracking params) and hydrator (clean)
    _add_source(
        conn, pid, "linkedin_email",
        "https://www.linkedin.com/comm/jobs/view/9999?alertAction=viewjob&trackingId=abc123"
    )
    _add_source(
        conn, pid, "linkedin_hydrator",
        "https://www.linkedin.com/jobs/view/9999"
    )
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    apply_count = fragment.count("Apply on LinkedIn")
    assert apply_count == 1, (
        f"Expected 1 Apply on LinkedIn button, got {apply_count} — "
        "email+hydrator rows for the same posting must collapse to one button"
    )
    # Hydrator URL must be used, not the tracking-laden email URL
    assert "trackingId" not in fragment, (
        "Hydrator URL should be preferred over email URL (no trackingId in rendered link)"
    )
    assert "https://www.linkedin.com/jobs/view/9999" in fragment, (
        "Clean hydrator URL must be rendered, not the email URL"
    )


def test_two_merged_postings_same_source_render_two_buttons(
    client: TestClient, db: Path
) -> None:
    """Two distinct postings (different job IDs) merged into one canonical,
    both LinkedIn, must render TWO Apply on LinkedIn buttons — one per posting."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid1, cid = _seed_canonical(conn, "Two LinkedIn Variants Test")
    _add_source(conn, pid1, "linkedin_hydrator", "https://www.linkedin.com/jobs/view/11111")

    # Second posting merged into the same canonical
    cur_p2 = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'Two LinkedIn Variants Test v2', 'complete', ?, ?)",
        (TS, TS),
    )
    pid2 = cur_p2.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 0.96, 'content_dedup', ?)",
        (pid2, cid, TS),
    )
    _add_source(conn, pid2, "linkedin_hydrator", "https://www.linkedin.com/jobs/view/22222")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    apply_count = fragment.count("Apply on LinkedIn")
    assert apply_count == 2, (
        f"Expected 2 Apply on LinkedIn buttons (one per merged posting), got {apply_count}"
    )
    assert "https://www.linkedin.com/jobs/view/11111" in fragment
    assert "https://www.linkedin.com/jobs/view/22222" in fragment


def test_canonical_id_chip_renders_on_card(client: TestClient, db: Path) -> None:
    """Each card must render a #canonical_id chip for triage/dev reference."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical(conn, "Chip Render Test")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert f"#{cid}" in fragment, (
        f"canonical_id chip '#{cid}' not found in card fragment"
    )
    assert "card-id-chip" in fragment, ".card-id-chip element missing from card"


def test_card_id_chip_css_rule_exists() -> None:
    """styles.css must define the .card-id-chip rule."""
    css_path = (
        Path(__file__).parents[2]
        / "src" / "jd_matcher" / "web" / "static" / "css" / "styles.css"
    )
    css = css_path.read_text()
    assert ".card-id-chip" in css, ".card-id-chip CSS rule missing from styles.css"


def test_badge_wording_is_variants_not_sources(client: TestClient, db: Path) -> None:
    """Badge wording for multi-variant canonical must say 'variants', not 'sources'."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid1, cid = _seed_canonical(conn, "Badge Wording Test")
    _add_source(conn, pid1, "linkedin_hydrator", "https://www.linkedin.com/jobs/view/77777")

    cur_p2 = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'Badge Wording Test v2', 'complete', ?, ?)",
        (TS, TS),
    )
    pid2 = cur_p2.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 0.96, 'repost', ?)",
        (pid2, cid, TS),
    )
    _add_source(conn, pid2, "linkedin_hydrator", "https://www.linkedin.com/jobs/view/88888")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "variants" in fragment, "Badge must use 'variants' wording"
    assert "2 sources" not in fragment, "Badge must not use old '2 sources' wording"


# ---------------------------------------------------------------------------
# TASK-M2-014 — LLM enrichment fields in card UI
# ---------------------------------------------------------------------------


def _seed_canonical_enriched(
    conn: sqlite3.Connection,
    title: str,
    *,
    seniority: str = "Senior",
    team: str | None = None,
    role_summary: str = "This role involves building ML systems at scale.",
    top_skills: list[str] | None = None,
    full_jd: str = "",
) -> tuple[int, int]:
    """Seed a canonical with all LLM enrichment fields configurable. Returns (pid, cid)."""
    skills_json = json.dumps(top_skills if top_skills is not None else [])
    cur_p = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen, full_jd)
        VALUES ('default', ?, 'complete', ?, ?, ?)
        """,
        (title, TS, TS, full_jd),
    )
    pid = cur_p.lastrowid
    cur_c = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_seniority,
             canonical_location, team_or_department, top_skills, role_summary, full_jd,
             full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', ?, 'EnrichCo', ?, 'Remote', ?, ?, ?, ?, '{}', ?, ?, '[]')
        """,
        (title, seniority, team, skills_json, role_summary, full_jd, TS, TS),
    )
    cid = cur_c.lastrowid
    conn.execute(
        """
        INSERT INTO posting_canonical_links
            (user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at)
        VALUES ('default', ?, ?, 1.0, 'new_canonical', ?)
        """,
        (pid, cid, TS),
    )
    return pid, cid


def test_seniority_chip_renders_when_present(client: TestClient, db: Path) -> None:
    """Card must render a .card-seniority-chip element when canonical_seniority is non-null."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Seniority Present", seniority="Senior")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-seniority-chip" in fragment, ".card-seniority-chip missing when seniority is set"
    assert "Senior" in fragment, "Seniority value 'Senior' not rendered in chip"


def test_seniority_chip_absent_when_null(client: TestClient, db: Path) -> None:
    """Card must NOT render .card-seniority-chip when canonical_seniority is null.

    canonical_seniority is NOT NULL in the schema, so we test via a seed that stores
    empty string — but the schema requires a value, so we use 'Mid' default from
    _seed_canonical and verify the chip is absent only when seniority=''.
    We seed with a non-null but empty-string seniority to trigger the null-guard.
    Actually, since canonical_seniority is NOT NULL in schema, we test the template's
    {% if posting.canonical_seniority %} guard using an empty string, which is falsy.
    """
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    # Insert with empty-string seniority (falsy in Jinja) to test the null-guard
    cur_p = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'No Seniority', 'complete', ?, ?)",
        (TS, TS),
    )
    pid = cur_p.lastrowid
    cur_c = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_seniority,
             canonical_location, top_skills, role_summary, full_jd,
             full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', 'No Seniority', 'TestCo', '',
                'Remote', '[]', 'A role.', '', '{}', ?, ?, '[]')
        """,
        (TS, TS),
    )
    cid = cur_c.lastrowid
    conn.execute(
        "INSERT INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 1.0, 'new_canonical', ?)",
        (pid, cid, TS),
    )
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-seniority-chip" not in fragment, (
        ".card-seniority-chip must be absent when canonical_seniority is empty/falsy"
    )


def test_team_or_department_renders_in_metadata_row(client: TestClient, db: Path) -> None:
    """Card must render team_or_department text in the .card-line2-meta dot-separated row."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(
        conn, "Team Present", team="Machine Learning Platform"
    )
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    # Team is now in the dot-separated metadata row (card-line2-meta), not a separate .card-team-line
    assert "card-line2-meta" in fragment, ".card-line2-meta missing when team_or_department is set"
    assert "Machine Learning Platform" in fragment, "Team name not rendered in metadata row"


def test_team_or_department_absent_when_null(client: TestClient, db: Path) -> None:
    """When team_or_department is null and location is present, metadata row shows only location."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "No Team", team=None)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    # Metadata row exists (location='Remote' still present) but no team dot-separator
    if "card-line2-meta" in fragment:
        meta_start = fragment.find("card-line2-meta")
        meta_end = fragment.find("</div>", meta_start)
        meta_fragment = fragment[meta_start:meta_end]
        assert " · " not in meta_fragment, (
            "Dot separator must not appear in metadata row when team is null"
        )


def test_role_summary_renders_in_full(client: TestClient, db: Path) -> None:
    """Card must render .card-role-summary with the full role_summary text — no truncation."""
    full_summary = (
        "This is a detailed role summary that exceeds two hundred characters and must be shown "
        "completely without any truncation or ellipsis, so the candidate understands the role "
        "before deciding to apply."
    )
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Long Summary", role_summary=full_summary)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-role-summary" in fragment, ".card-role-summary missing"
    # Full text must be present verbatim — no truncation applied
    assert full_summary in fragment, "Full role_summary text missing from card"
    # No ellipsis added by the template
    assert "…" not in fragment, "Unexpected truncation ellipsis found — truncate filter not removed"


def test_role_summary_absent_when_null(client: TestClient, db: Path) -> None:
    """Card must NOT render .card-role-summary when role_summary is empty/null."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Empty Summary", role_summary="")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-role-summary" not in fragment, (
        ".card-role-summary must be absent when role_summary is empty"
    )


def test_top_skills_strip_renders_in_collapsed_view(client: TestClient, db: Path) -> None:
    """Collapsed view (main page GET /) must show .card-skill-chip elements for each skill."""
    skills = ["Python", "SQL", "Machine Learning"]
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Skills Present", top_skills=skills)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-skills-strip" in fragment, ".card-skills-strip missing when top_skills is set"
    assert "card-skill-chip" in fragment, ".card-skill-chip elements missing from collapsed view"
    for skill in skills:
        assert skill in fragment, f"Skill '{skill}' not rendered in card fragment"


def test_top_skills_strip_absent_from_expanded_body(client: TestClient, db: Path) -> None:
    """The _card_jd_body.html expanded body must NOT render the skills strip (moved to collapsed)."""
    skills = ["Python", "SQL", "Machine Learning"]
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Skills Expanded Absent", top_skills=skills)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    # Locate the expanded body div within the card fragment
    expanded_start = fragment.find('class="card-expanded-body"')
    assert expanded_start != -1, ".card-expanded-body not found in card"
    expanded_fragment = fragment[expanded_start:]

    assert "card-skills-strip" not in expanded_fragment, (
        ".card-skills-strip must NOT appear inside .card-expanded-body — skills moved to collapsed view"
    )


def test_top_skills_strip_absent_when_empty(client: TestClient, db: Path) -> None:
    """Expanded view must NOT render .card-skills-strip when top_skills is empty list."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "No Skills", top_skills=[])
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-skills-strip" not in fragment, (
        ".card-skills-strip must be absent when top_skills is empty"
    )


def test_top_skills_strip_caps_at_10_chips(client: TestClient, db: Path) -> None:
    """When top_skills has 12 entries, only 10 chip elements must be rendered."""
    skills_12 = [f"Skill{i}" for i in range(1, 13)]  # Skill1 … Skill12
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "12 Skills", top_skills=skills_12)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    chip_count = fragment.count("card-skill-chip")
    assert chip_count == 10, (
        f"Expected 10 skill chips (cap), got {chip_count} — skills strip is not capped at 10"
    )
    # Skills 11 and 12 must not appear
    assert "Skill11" not in fragment, "Skill11 rendered — cap at 10 not enforced"
    assert "Skill12" not in fragment, "Skill12 rendered — cap at 10 not enforced"


def test_card_css_rules_for_new_elements_exist() -> None:
    """styles.css must define all CSS rules added by TASK-M2-014."""
    css_path = (
        Path(__file__).parents[2]
        / "src" / "jd_matcher" / "web" / "static" / "css" / "styles.css"
    )
    css = css_path.read_text()
    for rule in [
        ".card-seniority-chip",
        ".card-team-line",
        ".card-role-summary",
        ".card-skills-strip",
        ".card-skill-chip",
    ]:
        assert rule in css, f"CSS rule '{rule}' missing from styles.css"


# ---------------------------------------------------------------------------
# TASK-M2-015 — Collapsed-card layout reshuffle
# ---------------------------------------------------------------------------


def test_card_line_order(client: TestClient, db: Path) -> None:
    """Card DOM must have: line1 (title+company+id) before line2-meta before
    skills strip before role summary before line5 footer — in that order."""
    skills = ["Python", "SQL"]
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(
        conn,
        "Layout Order Test",
        seniority="Senior",
        team="ML Platform",
        role_summary="A test role at a great company.",
        top_skills=skills,
    )
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    pos_line1 = fragment.find("card-line1")
    pos_line2 = fragment.find("card-line2-meta")
    pos_skills = fragment.find("card-skills-strip")
    pos_summary = fragment.find("card-role-summary")
    pos_footer = fragment.find("card-line5-footer")

    assert pos_line1 != -1, "card-line1 not found"
    assert pos_line2 != -1, "card-line2-meta not found"
    assert pos_skills != -1, "card-skills-strip not found"
    assert pos_summary != -1, "card-role-summary not found"
    assert pos_footer != -1, "card-line5-footer not found"

    assert pos_line1 < pos_line2, "card-line1 must precede card-line2-meta"
    assert pos_line2 < pos_skills, "card-line2-meta must precede card-skills-strip"
    assert pos_skills < pos_summary, "card-skills-strip must precede card-role-summary"
    assert pos_summary < pos_footer, "card-role-summary must precede card-line5-footer"


def test_metadata_row_all_three_fields_present(client: TestClient, db: Path) -> None:
    """Line 2 must render 'Location · Team' when both location and team are present."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(
        conn, "Meta All Fields", team="Data Platform"
    )
    # _seed_canonical_enriched seeds location='Remote' and seniority='Senior' by default
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    meta_start = fragment.find("card-line2-meta")
    assert meta_start != -1, "card-line2-meta missing"
    meta_end = fragment.find("</div>", meta_start)
    meta_fragment = fragment[meta_start:meta_end]

    assert "Remote" in meta_fragment, "Location 'Remote' missing from metadata row"
    assert "Data Platform" in meta_fragment, "Team 'Data Platform' missing from metadata row"
    assert " · " in meta_fragment, "Dot separator missing from metadata row"
    # Ensure no stray double-dot or leading/trailing dot
    assert " ·  · " not in meta_fragment, "Stray double-dot in metadata row"


def test_metadata_row_missing_team(client: TestClient, db: Path) -> None:
    """Line 2 renders only location when team is null — no stray dot."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Meta No Team", team=None)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    meta_start = fragment.find("card-line2-meta")
    assert meta_start != -1, "card-line2-meta missing when location present"
    meta_end = fragment.find("</div>", meta_start)
    meta_fragment = fragment[meta_start:meta_end]

    assert "Remote" in meta_fragment, "Location missing from metadata row"
    assert " · " not in meta_fragment, (
        "Stray dot separator in metadata row when team is absent"
    )


def test_metadata_row_all_null(client: TestClient, db: Path) -> None:
    """Line 2 must be absent entirely when both location and team are null/empty."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    # Insert a canonical with empty location and null team
    cur_p = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen) "
        "VALUES ('default', 'No Meta', 'complete', ?, ?)",
        (TS, TS),
    )
    pid = cur_p.lastrowid
    cur_c = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_seniority,
             canonical_location, team_or_department, top_skills, role_summary, full_jd,
             full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', 'No Meta', 'TestCo', 'Mid',
                '', NULL, '[]', '', '', '{}', ?, ?, '[]')
        """,
        (TS, TS),
    )
    cid = cur_c.lastrowid
    conn.execute(
        "INSERT INTO posting_canonical_links "
        "(user_id, posting_id, canonical_id, similarity_score, merge_kind, merged_at) "
        "VALUES ('default', ?, ?, 1.0, 'new_canonical', ?)",
        (pid, cid, TS),
    )
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "card-line2-meta" not in fragment, (
        "card-line2-meta must be absent when both location and team are null/empty"
    )


def test_card_footer_sources_left_date_right(client: TestClient, db: Path) -> None:
    """Sources apply links and First-seen date must be in card-line5-footer (line 5)."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    pid, cid = _seed_canonical(conn, "Footer Test")
    _add_source(conn, pid, "linkedin", "https://linkedin.com/jobs/view/99999")
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    footer_start = fragment.find("card-line5-footer")
    assert footer_start != -1, "card-line5-footer missing from card"
    footer_end = fragment.find("</div>", footer_start)
    footer_fragment = fragment[footer_start:footer_end]

    assert "Sources:" in footer_fragment, "Sources: label must be in footer (line 5)"
    assert "Apply on LinkedIn" in footer_fragment, "Apply link must be in footer (line 5)"
    assert "First seen:" in footer_fragment, "First seen date must be in footer (line 5)"


def test_m2015_css_rules_exist() -> None:
    """styles.css must define .card-line2-meta, .card-line5-footer, .card-line1-right."""
    css_path = (
        Path(__file__).parents[2]
        / "src" / "jd_matcher" / "web" / "static" / "css" / "styles.css"
    )
    css = css_path.read_text()
    for rule in [
        ".card-line2-meta",
        ".card-line5-footer",
        ".card-line1-right",
    ]:
        assert rule in css, f"CSS rule '{rule}' missing from styles.css"


# ---------------------------------------------------------------------------
# TASK-M2-016 — Skills tiering: match-against-stack + category color + ordering
# ---------------------------------------------------------------------------


from jd_matcher.skills import (  # noqa: E402 — grouped with imports for readability
    CategorySpec,
    ClassifiedSkill,
    SkillCategoryMap,
    UserProfile,
    classify_and_sort_skills,
)


def _make_skill_map(
    *,
    ds_ml: list[str] | None = None,
    languages: list[str] | None = None,
    platforms: list[str] | None = None,
    aliases: dict[str, str] | None = None,
) -> SkillCategoryMap:
    """Build a minimal SkillCategoryMap for unit tests."""
    return SkillCategoryMap(
        categories={
            "ds_ml": CategorySpec(color="purple", css_class="skill-chip-ds", skills=ds_ml or []),
            "languages": CategorySpec(color="blue", css_class="skill-chip-lang", skills=languages or []),
            "platforms": CategorySpec(color="green", css_class="skill-chip-platform", skills=platforms or []),
            "other": CategorySpec(color="gray", css_class="skill-chip-other", skills=[]),
        },
        priority_order=["ds_ml", "languages", "platforms", "other"],
        alias_map=aliases or {},
    )


def _make_profile(core_skills: list[str]) -> UserProfile:
    return UserProfile(core_skills=core_skills, core_skills_normalized=set())


# ── Unit tests on classify_and_sort_skills ──────────────────────────────────


def test_classify_and_sort_skills_returns_correct_counts() -> None:
    """Direct unit test: match_count and total_count are accurate."""
    skill_map = _make_skill_map(
        ds_ml=["Machine Learning"],
        languages=["Python", "SQL"],
        platforms=["AWS"],
    )
    profile = _make_profile(["Python", "Machine Learning"])  # 2 of 4 match

    skills = ["Machine Learning", "Python", "SQL", "AWS"]
    classified, match_count, total_count = classify_and_sort_skills(skills, profile, skill_map)

    assert total_count == 4, f"total_count should be 4, got {total_count}"
    assert match_count == 2, f"match_count should be 2, got {match_count}"
    assert len(classified) == 4  # no cap needed for 4 skills


def test_alias_matching_genai_matches_generative_ai() -> None:
    """Card skill 'GenAI' must match user_profile entry 'Generative AI' via alias."""
    alias_map = {"genai": "generative ai", "generative ai": "generative ai"}
    skill_map = _make_skill_map(ds_ml=["Generative AI"], aliases=alias_map)
    profile = _make_profile(["Generative AI"])

    classified, match_count, total_count = classify_and_sort_skills(["GenAI"], profile, skill_map)

    assert match_count == 1, "GenAI should match via alias to Generative AI"
    assert classified[0].is_match is True
    assert classified[0].category == "ds_ml"


def test_alias_matching_case_insensitive() -> None:
    """Card skill 'python' (lowercase) must match user_profile 'Python'."""
    skill_map = _make_skill_map(languages=["Python"])
    profile = _make_profile(["Python"])

    classified, match_count, _ = classify_and_sort_skills(["python"], profile, skill_map)

    assert match_count == 1, "Case-insensitive match failed for 'python' vs 'Python'"
    assert classified[0].is_match is True


def test_skills_ordered_ds_then_lang_then_platform_then_other() -> None:
    """Matching skills must appear in ds_ml → languages → platforms → other order."""
    skill_map = _make_skill_map(
        ds_ml=["Machine Learning"],
        languages=["Python"],
        platforms=["AWS"],
    )
    profile = _make_profile(["Python", "Machine Learning", "AWS"])

    # Feed in reverse of expected priority order to confirm reordering
    skills = ["AWS", "Python", "Machine Learning"]
    classified, _, _ = classify_and_sort_skills(skills, profile, skill_map)

    categories = [cs.category for cs in classified]
    assert categories == ["ds_ml", "languages", "platforms"], (
        f"Expected [ds_ml, languages, platforms] ordering, got {categories}"
    )


def test_empty_user_profile_all_skills_render_as_nomatch() -> None:
    """With an empty core_skills, every skill must be is_match=False."""
    skill_map = _make_skill_map(languages=["Python", "SQL"])
    profile = _make_profile([])  # empty profile

    classified, match_count, total_count = classify_and_sort_skills(["Python", "SQL"], profile, skill_map)

    assert match_count == 0, "No skills should match an empty user profile"
    assert all(not cs.is_match for cs in classified), "All chips must have is_match=False"


def test_skills_capped_at_10_after_sorting() -> None:
    """With 15 skills (8 match + 7 non-match), cap at 10 must preserve all 8 matches."""
    skill_map = _make_skill_map(
        ds_ml=["ML1", "ML2", "ML3"],
        languages=["L1", "L2", "L3"],
        platforms=["P1", "P2"],
    )
    matching_skills = ["ML1", "ML2", "ML3", "L1", "L2", "L3", "P1", "P2"]  # 8 matches
    non_matching = ["NM1", "NM2", "NM3", "NM4", "NM5", "NM6", "NM7"]  # 7 non-matches
    profile = _make_profile(matching_skills)

    all_skills = matching_skills + non_matching  # 15 total, matches first in input too
    classified, match_count, total_count = classify_and_sort_skills(all_skills, profile, skill_map)

    assert total_count == 15, f"total_count should be 15, got {total_count}"
    assert match_count == 8, f"match_count should be 8, got {match_count}"
    assert len(classified) == 10, f"classified should be capped at 10, got {len(classified)}"
    # All 8 matches must be present (non-matches are sacrificed at the cap)
    rendered_match_skills = {cs.skill for cs in classified if cs.is_match}
    assert rendered_match_skills == set(matching_skills), (
        f"All 8 matches must survive the cap. Missing: {set(matching_skills) - rendered_match_skills}"
    )


def test_unknown_skill_falls_back_to_other_category() -> None:
    """A skill not in any category list must get category='other'."""
    skill_map = _make_skill_map(ds_ml=["Machine Learning"])
    profile = _make_profile([])

    classified, _, _ = classify_and_sort_skills(["SomeObscureSkill"], profile, skill_map)

    assert classified[0].category == "other", (
        f"Unknown skill should fall back to 'other', got {classified[0].category}"
    )
    assert classified[0].css_class == "skill-chip-other"


# ── HTML-level tests (require client + db fixture) ──────────────────────────


def test_match_skill_renders_with_category_color(client: TestClient, db: Path) -> None:
    """A skill in user's core_skills must render chip with both category class and skill-chip-match."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    # Python is in user_profile.yaml core_skills (languages category)
    _pid, cid = _seed_canonical_enriched(conn, "Match Color Test", top_skills=["Python"])
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "skill-chip-lang" in fragment, "Python must have skill-chip-lang category class"
    assert "skill-chip-match" in fragment, "Python (a core skill) must have skill-chip-match class"


def test_nonmatch_skill_renders_gray(client: TestClient, db: Path) -> None:
    """A skill NOT in user's core_skills must render with skill-chip-nomatch class."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    # Tableau is in platforms category but NOT in user's core_skills
    _pid, cid = _seed_canonical_enriched(conn, "Nomatch Gray Test", top_skills=["Tableau"])
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "skill-chip-nomatch" in fragment, "Tableau (not in core_skills) must have skill-chip-nomatch class"
    assert "skill-chip-platform" in fragment, "Tableau must still have its category class"


def test_skills_match_count_footer_renders(client: TestClient, db: Path) -> None:
    """Footer must show 'Skills match: X/Y' when classified_skills is non-empty."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    # 3 matching (Python, SQL, AWS) + 2 non-matching (Tableau, Data Governance)
    skills = ["Python", "SQL", "AWS", "Tableau", "Data Governance"]
    _pid, cid = _seed_canonical_enriched(conn, "Footer Count Test", top_skills=skills)
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "Skills match:" in fragment, "Skills match footer must be present"
    assert "3/5" in fragment, "Footer must show 3/5 (Python, SQL, AWS match; Tableau, Data Governance do not)"


def test_skills_match_count_zero_total_no_footer(client: TestClient, db: Path) -> None:
    """When top_skills is empty, the skills footer must be absent."""
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = ON;")
    _pid, cid = _seed_canonical_enriched(conn, "Empty Skills Footer Test", top_skills=[])
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{cid}"')
    assert card_start != -1, f"card-{cid} missing"
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]

    assert "Skills match:" not in fragment, "Footer must be absent when top_skills is empty"
    assert "card-skills-footer" not in fragment, "card-skills-footer must be absent when no skills"


def test_m2016_css_rules_exist() -> None:
    """styles.css must define all CSS rules added by TASK-M2-016."""
    css_path = (
        Path(__file__).parents[2]
        / "src" / "jd_matcher" / "web" / "static" / "css" / "styles.css"
    )
    css = css_path.read_text()
    for rule in [
        ".card-skill-chip.skill-chip-nomatch",
        ".card-skill-chip.skill-chip-ds.skill-chip-match",
        ".card-skill-chip.skill-chip-lang.skill-chip-match",
        ".card-skill-chip.skill-chip-platform.skill-chip-match",
        ".card-skill-chip.skill-chip-other.skill-chip-match",
        ".card-skills-footer",
    ]:
        assert rule in css, f"CSS rule '{rule}' missing from styles.css"
