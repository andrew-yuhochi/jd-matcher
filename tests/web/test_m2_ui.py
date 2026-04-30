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
    assert "2 sources" in fragment, "Source count '2 sources' text missing"


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
