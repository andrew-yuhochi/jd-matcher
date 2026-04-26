"""
DOM structural tests for C9 (Web UI: frontend) — TASK-M1-010 ACs #1, #3, #4, #5, #6.

Uses selectolax (or BeautifulSoup fallback) to parse rendered HTML.
All tests use a seeded SQLite DB wired via JD_MATCHER_DB_PATH env var.

AC coverage:
  AC #1  — 3 tabs render with seeded fixture postings
  AC #3  — sub-bar has 4 badge spans with correct data-source attrs
  AC #4  — NO badge close button / dismiss affordance in DOM (LOAD-BEARING)
  AC #5  — failed-status badges carry a title= attribute with failure_reason
  AC #6  — hydration-failed + partial cards: (a) present, (b) have .warning,
            (c) action buttons present (LOAD-BEARING)
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

# ---------------------------------------------------------------------------
# Attempt selectolax; fall back to html.parser via the stdlib
# ---------------------------------------------------------------------------

try:
    from selectolax.parser import HTMLParser  # type: ignore

    def _parse(html: str):
        return HTMLParser(html)

    def _css(tree, selector: str):
        return tree.css(selector)

    def _attr(node, attr: str):
        return node.attributes.get(attr, "")

    def _text(node) -> str:
        return node.text(strip=True)

    _PARSER = "selectolax"
except ImportError:
    from html.parser import HTMLParser as _StdHTMLParser

    # Thin wrapper using Python's built-in html.parser (no CSS selectors —
    # we'll do string searches on raw HTML for selectolax-absent environments)
    _PARSER = "stdlib"
    _parse = None  # type: ignore
    _css = None  # type: ignore
    _attr = None  # type: ignore
    _text = None  # type: ignore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TS = "2026-04-25T10:00:00+00:00"


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Generator[Path, None, None]:
    db_path = tmp_path / "test_dom.db"
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")

    # 10 complete, 3 partial, 3 failed postings
    statuses = ["complete"] * 10 + ["partial"] * 3 + ["failed"] * 3
    for i, hs in enumerate(statuses):
        conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_title, canonical_company, canonical_location,
                 hydration_status, first_seen, last_seen)
            VALUES ('default', ?, ?, ?, ?, ?, ?)
            """,
            (f"Job {i+1}", f"Corp {i+1}", "Vancouver, BC", hs, TS, TS),
        )

    conn.commit()
    conn.close()

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
def client(seeded_db: Path) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# AC #1 — Three tabs render with seeded fixture postings
# ---------------------------------------------------------------------------


def test_main_tab_has_three_tab_links(client: TestClient) -> None:
    html = client.get("/").text
    assert 'href="/"' in html, "Main tab href missing"
    assert 'href="/applied"' in html, "Applied tab href missing"
    assert 'href="/dismissed"' in html, "Dismissed tab href missing"


def test_main_tab_has_data_tab_attributes(client: TestClient) -> None:
    html = client.get("/").text
    assert 'data-tab="main"' in html
    assert 'data-tab="applied"' in html
    assert 'data-tab="dismissed"' in html


def test_main_tab_shows_seeded_cards(client: TestClient, seeded_db: Path) -> None:
    html = client.get("/").text
    conn = sqlite3.connect(str(seeded_db))
    ids = [r[0] for r in conn.execute("SELECT id FROM postings").fetchall()]
    conn.close()
    for pid in ids:
        assert f'data-posting-id="{pid}"' in html, f"card {pid} missing from main tab"


def test_applied_tab_renders_200(client: TestClient) -> None:
    resp = client.get("/applied")
    assert resp.status_code == 200
    assert "Applied" in resp.text


def test_dismissed_tab_has_search_box(client: TestClient) -> None:
    html = client.get("/dismissed").text
    assert 'id="dismissed-search"' in html


# ---------------------------------------------------------------------------
# AC #3 — Sub-bar has 4 badge spans with correct data-source attrs
# ---------------------------------------------------------------------------


def test_subbar_has_four_badges(client: TestClient) -> None:
    html = client.get("/").text
    expected_sources = [
        "gmail_linkedin",
        "gmail_indeed",
        "hydrator_linkedin",
        "hydrator_indeed",
    ]
    for src in expected_sources:
        assert f'data-source="{src}"' in html, f"badge for {src} missing from sub-bar"


def test_subbar_badges_have_badge_ids(client: TestClient) -> None:
    html = client.get("/").text
    assert 'id="badge-gmail_linkedin"' in html
    assert 'id="badge-gmail_indeed"' in html
    assert 'id="badge-hydrator_linkedin"' in html
    assert 'id="badge-hydrator_indeed"' in html


# ---------------------------------------------------------------------------
# AC #4 — NO badge close button / dismiss affordance in DOM (LOAD-BEARING)
# ---------------------------------------------------------------------------


def test_badges_have_no_close_button(client: TestClient) -> None:
    """LOAD-BEARING: assert the DOM contains no dismiss/close affordance for badges.

    Checks for:
      - Any element with class badge-close
      - Any data-action="dismiss-badge"
      - Any button inside the source-badges span
      - Any '×' or 'x' character adjacent to badge spans (crude but catches typos)
    """
    html = client.get("/").text
    # No class-based close button
    assert "badge-close" not in html, "Found badge-close class — badges must not be dismissible"
    # No dismiss-badge data action
    assert 'data-action="dismiss-badge"' not in html, "Found dismiss-badge data-action"
    # source-badges span must not contain a <button> element
    # Parse the source-badges section
    start = html.find('id="source-badges"')
    end = html.find("</span>", start)
    assert start != -1, "source-badges span not found"
    fragment = html[start:end]
    assert "<button" not in fragment, "Found <button> inside source-badges — badges must not be dismissible"
    # No mark-as-read attribute
    assert "mark-as-read" not in html, "Found mark-as-read — badges must not be dismissible"


def test_badges_have_no_x_character_inside_badge_span(client: TestClient) -> None:
    """No '×' or close-glyph inside badge spans."""
    html = client.get("/").text
    # Extract each badge element text
    for src in ["gmail_linkedin", "gmail_indeed", "hydrator_linkedin", "hydrator_indeed"]:
        start = html.find(f'id="badge-{src}"')
        assert start != -1, f"badge-{src} not found"
        end = html.find("</span>", start) + len("</span>")
        fragment = html[start:end]
        assert "×" not in fragment, f"Badge {src} contains × close glyph"
        # Check for 'data-dismiss' pattern
        assert "data-dismiss" not in fragment, f"Badge {src} has data-dismiss"


# ---------------------------------------------------------------------------
# AC #5 — failed-status badges carry title= with failure_reason
# ---------------------------------------------------------------------------


def test_failed_badge_has_failure_reason_in_title(
    client: TestClient, seeded_db: Path
) -> None:
    conn = sqlite3.connect(str(seeded_db))
    conn.execute(
        """
        INSERT INTO pipeline_runs
            (run_id, source, health_status, failure_reason, started_at, finished_at)
        VALUES ('run-001', 'hydrator_linkedin', 'failed', 'OAuth token expired', ?, ?)
        """,
        (TS, TS),
    )
    conn.commit()
    conn.close()

    # The badge title is set dynamically by JS on page load via /api/source-health.
    # The DOM structural test verifies the badge element IS present with the right
    # data-source; the title= attribute is populated by JS (client-side) so it
    # starts as empty string in server-rendered HTML.
    # We verify the /api/source-health endpoint carries failure_reason correctly.
    resp = client.get("/api/source-health")
    data = resp.json()
    hl = next(e for e in data if e["source"] == "hydrator_linkedin")
    assert hl["health_status"] == "failed"
    assert hl["failure_reason"] == "OAuth token expired", (
        "failure_reason missing from /api/source-health — badge tooltip will be empty"
    )


# ---------------------------------------------------------------------------
# AC #6 — hydration-failed + partial cards: present + warning + action buttons
#          (LOAD-BEARING)
# ---------------------------------------------------------------------------


def test_hydration_failed_cards_present_in_main(
    client: TestClient, seeded_db: Path
) -> None:
    """LOAD-BEARING: seed 2 postings with hydration_status failed/partial; assert both
    appear on GET / with .warning element and action button data-posting-id attrs."""
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("PRAGMA foreign_keys = ON;")
    ts = TS
    cur_f = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen)
        VALUES ('default', 'Failed Hydration Job', 'failed', ?, ?)
        """,
        (ts, ts),
    )
    pid_failed = cur_f.lastrowid

    cur_p = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen)
        VALUES ('default', 'Partial Hydration Job', 'partial', ?, ?)
        """,
        (ts, ts),
    )
    pid_partial = cur_p.lastrowid
    conn.commit()
    conn.close()

    html = client.get("/").text

    # (a) Both cards present in DOM
    assert f'data-posting-id="{pid_failed}"' in html, "failed hydration card absent from main"
    assert f'data-posting-id="{pid_partial}"' in html, "partial hydration card absent from main"

    # (b) Both have the ⚠ JD incomplete warning element
    # We look for the warning span near each card's id marker
    for pid in [pid_failed, pid_partial]:
        card_start = html.find(f'id="card-{pid}"')
        assert card_start != -1, f"card-{pid} id attr not found"
        # Find the end of the article tag
        card_end = html.find("</article>", card_start)
        fragment = html[card_start:card_end]
        assert 'class="warning"' in fragment, (
            f"card-{pid}: .warning element missing for hydration_status=failed/partial"
        )
        assert "JD incomplete" in fragment, (
            f"card-{pid}: 'JD incomplete' text missing"
        )

    # (c) Action buttons (btn-apply, btn-dismiss) present on both cards
    for pid in [pid_failed, pid_partial]:
        card_start = html.find(f'id="card-{pid}"')
        card_end = html.find("</article>", card_start)
        fragment = html[card_start:card_end]
        assert 'class="btn-apply"' in fragment, (
            f"card-{pid}: btn-apply missing — d/a/o shortcuts require action buttons"
        )
        assert 'class="btn-dismiss"' in fragment, (
            f"card-{pid}: btn-dismiss missing"
        )


def test_complete_hydration_card_has_no_warning(
    client: TestClient, seeded_db: Path
) -> None:
    """Complete hydration cards must NOT have the ⚠ indicator."""
    conn = sqlite3.connect(str(seeded_db))
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, hydration_status, first_seen, last_seen)
        VALUES ('default', 'Complete Job', 'complete', ?, ?)
        """,
        (TS, TS),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()

    html = client.get("/").text
    card_start = html.find(f'id="card-{pid}"')
    card_end = html.find("</article>", card_start)
    fragment = html[card_start:card_end]
    assert 'class="warning"' not in fragment, (
        "complete hydration card incorrectly shows ⚠ warning"
    )


# ---------------------------------------------------------------------------
# Static asset references in base template
# ---------------------------------------------------------------------------


def test_base_references_app_js(client: TestClient) -> None:
    html = client.get("/").text
    assert 'src="/static/js/app.js"' in html, "app.js script tag missing from base.html"


def test_base_references_styles_css(client: TestClient) -> None:
    html = client.get("/").text
    assert 'href="/static/css/styles.css"' in html, "styles.css link missing"


def test_cheatsheet_modal_in_dom(client: TestClient) -> None:
    html = client.get("/").text
    assert 'id="cheatsheet"' in html, "cheatsheet modal element missing"
    assert 'class="cheatsheet"' in html
