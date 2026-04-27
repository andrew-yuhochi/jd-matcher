"""
Structural tests for keyboard handler JS (C9) — TASK-M1-010 AC #2, #8.

Playwright is NOT installed in this environment (no browser binary).
Per TDD §C9 quality (a): "manual smoke is explicitly allowed."

This test file provides:
  1. Structural verification that app.js exists and is referenced correctly.
  2. Static analysis of app.js for required handler branches.
  3. API-level integration tests confirming the backend endpoints the
     keyboard handler calls actually work (the JS-path endpoints).

Browser-based keyboard interaction is documented in the quality log
(docs/poc/quality-logs/TASK-M1-010.md) as requiring manual verification
at the M1 demo (TASK-M1-012).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from jd_matcher.db.init_db import init_db
from jd_matcher.web.app import app

APP_JS = Path(
    "/Users/andrew.yu/personal/new-structure/projects/jd-matcher"
    "/src/jd_matcher/web/static/js/app.js"
)
TS = "2026-04-25T10:00:00+00:00"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Generator[Path, None, None]:
    db_path = tmp_path / "test_kb.db"
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    for i in range(5):
        conn.execute(
            """
            INSERT INTO postings
                (user_id, canonical_title, canonical_company,
                 canonical_location, hydration_status, first_seen, last_seen)
            VALUES ('default', ?, ?, ?, ?, ?, ?)
            """,
            (f"KB Job {i+1}", f"Corp {i+1}", "Vancouver, BC", "complete", TS, TS),
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
# AC #8 (structural) — app.js exists and is correctly referenced
# ---------------------------------------------------------------------------


def test_app_js_exists() -> None:
    assert APP_JS.exists(), f"app.js not found at {APP_JS}"


def test_base_html_references_app_js(client: TestClient) -> None:
    html = client.get("/").text
    assert 'src="/static/js/app.js"' in html


def test_app_js_endpoint_serves_200(client: TestClient) -> None:
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "").lower()


# ---------------------------------------------------------------------------
# Static analysis of app.js — required keyboard handler branches
# ---------------------------------------------------------------------------


def _js_source() -> str:
    return APP_JS.read_text(encoding="utf-8")


def test_app_js_handles_j_key() -> None:
    src = _js_source()
    assert '"j"' in src or "'j'" in src, "app.js missing 'j' key handler"


def test_app_js_handles_k_key() -> None:
    src = _js_source()
    assert '"k"' in src or "'k'" in src, "app.js missing 'k' key handler"


def test_app_js_handles_e_key() -> None:
    src = _js_source()
    assert '"e"' in src or "'e'" in src, "app.js missing 'e' key handler"


def test_app_js_handles_d_key() -> None:
    src = _js_source()
    assert '"d"' in src or "'d'" in src, "app.js missing 'd' key handler"


def test_app_js_handles_a_key() -> None:
    src = _js_source()
    assert '"a"' in src or "'a'" in src, "app.js missing 'a' key handler"


def test_app_js_handles_o_key() -> None:
    src = _js_source()
    assert '"o"' in src or "'o'" in src, "app.js missing 'o' key handler"


def test_app_js_handles_1_2_3_keys() -> None:
    src = _js_source()
    assert '"1"' in src, "app.js missing '1' key for tab switch"
    assert '"2"' in src, "app.js missing '2' key for tab switch"
    assert '"3"' in src, "app.js missing '3' key for tab switch"


def test_app_js_handles_question_key() -> None:
    src = _js_source()
    assert '"?"' in src or "'?'" in src, "app.js missing '?' cheatsheet key"


def test_app_js_handles_escape_key() -> None:
    src = _js_source()
    assert '"Escape"' in src or "'Escape'" in src, "app.js missing Escape handler"


def test_app_js_emits_session_start() -> None:
    src = _js_source()
    assert "session_start" in src, "app.js must emit session_start on page load"


def test_app_js_emits_card_dismissed() -> None:
    src = _js_source()
    assert "card_dismissed" in src, "app.js must emit card_dismissed"


def test_app_js_emits_card_marked_applied() -> None:
    src = _js_source()
    assert "card_marked_applied" in src, "app.js must emit card_marked_applied"


def test_app_js_emits_tab_switched() -> None:
    src = _js_source()
    assert "tab_switched" in src, "app.js must emit tab_switched"


def test_app_js_includes_time_to_decide_ms() -> None:
    src = _js_source()
    assert "time_to_decide_ms" in src, "app.js must compute time_to_decide_ms"


def test_app_js_includes_session_id() -> None:
    src = _js_source()
    assert "SESSION_ID" in src or "session_id" in src, "app.js must include session_id in events"


def test_app_js_dismissing_css_class_applied() -> None:
    src = _js_source()
    assert "dismissing" in src, "app.js must add 'dismissing' CSS class for slide-left animation"


def test_app_js_applying_css_class_applied() -> None:
    src = _js_source()
    assert "applying" in src, "app.js must add 'applying' CSS class for fade-out animation"


def test_app_js_no_close_button_added_to_badges() -> None:
    """Badge update function must NOT inject any close/dismiss button into the DOM."""
    src = _js_source()
    # Locate the updateBadge function body (stop at first closing brace on its own line)
    match = re.search(r"function updateBadge\b.*?\n\}", src, re.DOTALL)
    if match:
        badge_fn = match.group(0)
        # Check for DOM-injection patterns (innerHTML, createElement, appendChild)
        # that could add a close button — not comments.
        close_patterns = [
            r'innerHTML.*close',
            r'createElement.*button',
            r'appendChild.*close',
            r'insertAdjacentHTML.*close',
        ]
        for pattern in close_patterns:
            assert not re.search(pattern, badge_fn, re.IGNORECASE), (
                f"updateBadge() appears to inject a close button (pattern: {pattern!r})"
            )


def test_e_shortcut_not_guarded_by_dismissed_tab() -> None:
    """e (expand) must work on Dismissed tab — no isDismissedTab guard."""
    src = _js_source()
    # Locate the 'e' case block
    match = re.search(r'case "e":(.*?)break;', src, re.DOTALL)
    assert match, "app.js missing 'e' case block"
    assert "isDismissedTab" not in match.group(1), (
        "e shortcut must NOT contain isDismissedTab guard (should work on Dismissed tab)"
    )


def test_o_shortcut_not_guarded_by_dismissed_tab() -> None:
    """o (open URL) must work on Dismissed tab — no isDismissedTab guard."""
    src = _js_source()
    match = re.search(r'case "o":(.*?)break;', src, re.DOTALL)
    assert match, "app.js missing 'o' case block"
    assert "isDismissedTab" not in match.group(1), (
        "o shortcut must NOT contain isDismissedTab guard (should work on Dismissed tab)"
    )


def test_d_shortcut_still_guarded_by_dismissed_tab() -> None:
    """d (dismiss) must remain disabled on Dismissed tab."""
    src = _js_source()
    match = re.search(r'case "d":(.*?)break;', src, re.DOTALL)
    assert match, "app.js missing 'd' case block"
    assert "isDismissedTab" in match.group(1), (
        "d shortcut MUST contain isDismissedTab guard (already dismissed; no-op on that tab)"
    )


def test_a_shortcut_still_guarded_by_dismissed_tab() -> None:
    """a (apply) must remain disabled on Dismissed tab — restore-first per state model."""
    src = _js_source()
    match = re.search(r'case "a":(.*?)break;', src, re.DOTALL)
    assert match, "app.js missing 'a' case block"
    assert "isDismissedTab" in match.group(1), (
        "a shortcut MUST contain isDismissedTab guard (restore-first per state model)"
    )


def test_app_js_uses_intersection_observer() -> None:
    src = _js_source()
    assert "IntersectionObserver" in src, (
        "app.js must use IntersectionObserver to record card_viewed timestamps"
    )


# ---------------------------------------------------------------------------
# API-level integration: keyboard-driven backend calls work end-to-end
# ---------------------------------------------------------------------------


def test_dismiss_endpoint_callable_from_js_path(
    client: TestClient, seeded_db: Path
) -> None:
    """The JS 'd' handler calls POST /postings/{id}/dismiss — verify it works."""
    conn = sqlite3.connect(str(seeded_db))
    cur = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen)"
        " VALUES ('default', 'JS Dismiss Test', 'complete', ?, ?)",
        (TS, TS),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()

    resp = client.post(f"/postings/{pid}/dismiss")
    assert resp.status_code == 200

    conn = sqlite3.connect(str(seeded_db))
    count = conn.execute(
        "SELECT count(*) FROM dismissed WHERE posting_id = ?", (pid,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_apply_endpoint_callable_from_js_path(
    client: TestClient, seeded_db: Path
) -> None:
    """The JS 'a' handler calls POST /postings/{id}/apply — verify it works."""
    conn = sqlite3.connect(str(seeded_db))
    cur = conn.execute(
        "INSERT INTO postings (user_id, canonical_title, hydration_status, first_seen, last_seen)"
        " VALUES ('default', 'JS Apply Test', 'complete', ?, ?)",
        (TS, TS),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()

    resp = client.post(f"/postings/{pid}/apply")
    assert resp.status_code == 200

    conn = sqlite3.connect(str(seeded_db))
    count = conn.execute(
        "SELECT count(*) FROM applied WHERE posting_id = ?", (pid,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_events_endpoint_callable_from_js_path(
    client: TestClient, seeded_db: Path
) -> None:
    """The JS emitEvent() function calls POST /api/events — verify it works."""
    resp = client.post(
        "/api/events",
        json={
            "event_type": "card_dismissed",
            "posting_id": 1,
            "metadata": {"time_to_decide_ms": 3200},
            "session_id": "js-path-test",
        },
    )
    assert resp.status_code == 204

    conn = sqlite3.connect(str(seeded_db))
    row = conn.execute(
        "SELECT event_type, session_id FROM events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == "card_dismissed"
    assert row[1] == "js-path-test"


def test_source_health_endpoint_callable_from_js_path(
    client: TestClient,
) -> None:
    """The JS fetchSourceHealth() calls GET /api/source-health — verify shape."""
    resp = client.get("/api/source-health")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    sources = {e["source"] for e in data}
    assert "gmail_linkedin" in sources


# ---------------------------------------------------------------------------
# Manual smoke test documentation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Click-to-select — static analysis (Feature 1)
# ---------------------------------------------------------------------------


def test_app_js_has_click_handler_on_card_containers() -> None:
    """app.js must wire a click handler to card list containers."""
    src = _js_source()
    assert "handleCardContainerClick" in src, (
        "app.js must define and register handleCardContainerClick"
    )
    assert "addEventListener" in src, (
        "app.js must register click event listener"
    )


def test_app_js_action_buttons_call_stop_propagation() -> None:
    """Action buttons (apply/dismiss/restore/unapply) must call stopPropagation."""
    src = _js_source()
    assert "stopPropagation" in src, (
        "app.js must call e.stopPropagation() on action button click handlers "
        "so card click does not also fire"
    )


def test_app_js_has_unapply_handler() -> None:
    """app.js must have a click handler for .btn-unapply."""
    src = _js_source()
    assert "btn-unapply" in src, "app.js missing .btn-unapply handler"
    assert "/unapply" in src, "app.js must POST to /postings/{id}/unapply"


def test_manual_smoke_note_is_documented() -> None:
    """
    DOCUMENTATION TEST: This test exists to assert that the manual smoke test
    requirement is acknowledged. Browser-based keyboard interaction CANNOT be
    verified by data-pipeline (no browser access).

    Required manual verification at M1 demo (TASK-M1-012):
      1. Open http://localhost:8765/ with seeded data
      2. Press j/k — verify focus ring moves between cards
      3. Press e on focused card — verify card expands (shows expanded-body section)
      4. Press e again — verify card collapses
      5. Press d — verify 180ms slide-left animation, card removed, focus moves to next
      6. Press a — verify 150ms fade-out, card removed from list
      7. Press o — verify apply URL opens in new tab
      8. Press 1/2/3 — verify tab navigation
      9. Press ? — verify cheatsheet modal appears
      10. Press Esc — verify cheatsheet closes / expanded card collapses
      11. sqlite3 ~/.jd-matcher/jd-matcher.db "SELECT event_type, count(*) FROM events GROUP BY event_type"
          verify rows for card_viewed, card_dismissed, card_marked_applied, tab_switched, session_start

    This documents the gap. test-validator will verify via Playwright if available
    at TASK-M1-012.
    """
    # This assertion always passes — it documents the manual test requirement.
    assert True, "Manual smoke test requirement acknowledged"
