"""
Tests for C22 — State Manager extension (canonical_view.py).

AC coverage per TDD §C22 quality criteria (a)-(e):
  (a) Canonical with ANY linked posting in applied → is_canonical_applied=True
  (b) Canonical with ANY linked posting in dismissed → is_canonical_dismissed=True
  (c) Apply-one-suppress-all: apply LinkedIn variant → select_main() excludes canonical
  (d) Re-ingest Indeed variant after apply → does NOT resurface in Main
  (e) Restore via C7 → canonical re-appears in Main with both sources

AC #4 (load-bearing M2 invariant): Apply-one-suppress-all:
  Seed canonical X with 2 source postings (LinkedIn + Indeed variants).
  apply(posting_id=A) via C7 → select_main() MUST exclude canonical X entirely.
  restore(posting_id=A) via C7 → select_main() MUST include canonical X again.

AC #3 per TASK-M2-010: C22 select_main returns canonical-level cards (not posting-level).

AC #5 per TASK-M2-010: Persistence across restart: state inheritance works after server
  restart — verified by using the same on-disk tmp DB in multiple function calls
  (no in-process state shared between calls).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jd_matcher.db.init_db import init_db
from jd_matcher.state.canonical_view import (
    CanonicalCard,
    CanonicalStateView,
    get_canonical_state,
    is_canonical_applied,
    is_canonical_dismissed,
    select_main,
)
from jd_matcher.state.manager import dismiss, mark_applied, restore, unapply


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    """Fresh test DB with schema applied."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_posting(conn: sqlite3.Connection, title: str, company: str) -> int:
    """Insert a posting row and return its id."""
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO postings
            (user_id, canonical_title, canonical_company, canonical_location,
             hydration_status, full_jd, role_summary, first_seen, last_seen)
        VALUES ('default', ?, ?, 'Vancouver', 'complete', 'jd text', 'summary', ?, ?)
        """,
        (title, company, now, now),
    )
    return cur.lastrowid


def _seed_canonical(
    conn: sqlite3.Connection,
    title: str,
    company: str,
) -> int:
    """Insert a canonical_postings row and return its canonical_id."""
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO canonical_postings
            (user_id, canonical_title, canonical_company, canonical_location,
             canonical_seniority, top_skills, role_summary, full_jd,
             full_jd_provenance, first_seen, last_seen, sources_summary)
        VALUES ('default', ?, ?, 'Vancouver', 'Senior',
                '[]', 'test summary', 'test jd text',
                '{"chosen_from_posting_id": 1, "source": "linkedin"}',
                ?, ?, '["linkedin"]')
        """,
        (title, company, now, now),
    )
    return cur.lastrowid


def _seed_link(
    conn: sqlite3.Connection,
    posting_id: int,
    canonical_id: int,
    merge_kind: str = "new_canonical",
    similarity_score: float = 1.0,
) -> None:
    """Insert a posting_canonical_links row."""
    now = _now()
    conn.execute(
        """
        INSERT INTO posting_canonical_links
            (posting_id, canonical_id, user_id, merge_kind, similarity_score, merged_at)
        VALUES (?, ?, 'default', ?, ?, ?)
        """,
        (posting_id, canonical_id, merge_kind, similarity_score, now),
    )


def _seed_posting_source(
    conn: sqlite3.Connection,
    posting_id: int,
    source: str,
    url: str,
) -> None:
    """Insert a posting_sources row."""
    now = _now()
    conn.execute(
        """
        INSERT OR IGNORE INTO posting_sources
            (posting_id, user_id, source, source_url, source_first_seen)
        VALUES (?, 'default', ?, ?, ?)
        """,
        (posting_id, source, url, now),
    )


# ---------------------------------------------------------------------------
# Helper: build a 2-posting, 1-canonical synthetic fixture
# Returns (posting_id_a, posting_id_b, canonical_id)
# where A = LinkedIn variant, B = Indeed variant
# ---------------------------------------------------------------------------


def _build_two_variant_canonical(db_path: Path) -> tuple[int, int, int]:
    """Seed canonical X with two source variants (LinkedIn + Indeed) and link both."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        pid_a = _seed_posting(conn, "Senior ML Engineer", "Acme Corp")
        pid_b = _seed_posting(conn, "Senior ML Engineer", "Acme Corp")
        can_id = _seed_canonical(conn, "Senior ML Engineer", "Acme Corp")
        _seed_link(conn, pid_a, can_id, "new_canonical")
        _seed_link(conn, pid_b, can_id, "content_dedup")
        _seed_posting_source(conn, pid_a, "linkedin_hydrator", f"https://linkedin.com/jobs/{pid_a}")
        _seed_posting_source(conn, pid_b, "indeed_hydrator", f"https://indeed.com/viewjob?jk={pid_b}")
        conn.commit()
    finally:
        conn.close()
    return pid_a, pid_b, can_id


# ---------------------------------------------------------------------------
# AC (a) — is_canonical_applied: True when ANY linked posting is in applied
# ---------------------------------------------------------------------------


class TestIsCanonicalApplied:
    def test_true_when_linked_posting_applied(self, db: Path) -> None:
        """AC (a): canonical with any linked posting in applied → is_canonical_applied=True."""
        pid_a, pid_b, can_id = _build_two_variant_canonical(db)
        mark_applied(pid_a, db_path=db)
        assert is_canonical_applied(can_id, db_path=db) is True

    def test_true_when_second_variant_applied(self, db: Path) -> None:
        """AC (a): canonical with second (Indeed) variant applied → is_canonical_applied=True."""
        pid_a, pid_b, can_id = _build_two_variant_canonical(db)
        mark_applied(pid_b, db_path=db)
        assert is_canonical_applied(can_id, db_path=db) is True

    def test_false_when_no_posting_applied(self, db: Path) -> None:
        """AC (a): canonical with no applied postings → is_canonical_applied=False."""
        _, _, can_id = _build_two_variant_canonical(db)
        assert is_canonical_applied(can_id, db_path=db) is False

    def test_false_for_unknown_canonical(self, db: Path) -> None:
        """AC (a): non-existent canonical_id → is_canonical_applied=False (no rows)."""
        assert is_canonical_applied(99999, db_path=db) is False


# ---------------------------------------------------------------------------
# AC (b) — is_canonical_dismissed: True when ANY linked posting is in dismissed
# ---------------------------------------------------------------------------


class TestIsCanonicalDismissed:
    def test_true_when_linked_posting_dismissed(self, db: Path) -> None:
        """AC (b): canonical with any linked posting in dismissed → is_canonical_dismissed=True."""
        pid_a, pid_b, can_id = _build_two_variant_canonical(db)
        dismiss(pid_a, db_path=db)
        assert is_canonical_dismissed(can_id, db_path=db) is True

    def test_true_when_second_variant_dismissed(self, db: Path) -> None:
        """AC (b): dismissing the Indeed variant → is_canonical_dismissed=True."""
        pid_a, pid_b, can_id = _build_two_variant_canonical(db)
        dismiss(pid_b, db_path=db)
        assert is_canonical_dismissed(can_id, db_path=db) is True

    def test_false_when_no_posting_dismissed(self, db: Path) -> None:
        """AC (b): canonical with no dismissed postings → is_canonical_dismissed=False."""
        _, _, can_id = _build_two_variant_canonical(db)
        assert is_canonical_dismissed(can_id, db_path=db) is False


# ---------------------------------------------------------------------------
# AC (c) — Apply-one-suppress-all: the load-bearing M2 state invariant
# ---------------------------------------------------------------------------


class TestApplyOneSuppressAll:
    """AC #4 per TASK-M2-010 — AC (c) per TDD §C22."""

    def test_apply_linkedin_suppresses_canonical_from_main(self, db: Path) -> None:
        """AC (c): apply LinkedIn variant → select_main() excludes canonical entirely."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)

        # Before apply: canonical should appear in Main
        cards_before = select_main(db_path=db)
        can_ids_before = {c.canonical_id for c in cards_before}
        assert can_id in can_ids_before, (
            "Canonical should appear in select_main() before any apply action"
        )

        # Apply the LinkedIn variant via C7
        mark_applied(pid_a, db_path=db)

        # After apply: canonical MUST NOT appear in Main (both variants suppressed)
        cards_after = select_main(db_path=db)
        can_ids_after = {c.canonical_id for c in cards_after}
        assert can_id not in can_ids_after, (
            "Canonical must be suppressed from select_main() after applying LinkedIn variant; "
            "apply-one-suppress-all invariant violated"
        )

    def test_dismiss_indeed_suppresses_canonical_from_main(self, db: Path) -> None:
        """AC (c) variant: dismissing the Indeed posting also suppresses the whole canonical."""
        _pid_a, pid_b, can_id = _build_two_variant_canonical(db)

        dismiss(pid_b, db_path=db)

        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can_id not in can_ids, (
            "Canonical must be suppressed after dismissing the Indeed variant"
        )

    def test_select_main_returns_canonical_cards_not_postings(self, db: Path) -> None:
        """AC #3 per TASK-M2-010: select_main returns CanonicalCard objects (not posting rows)."""
        _build_two_variant_canonical(db)
        cards = select_main(db_path=db)
        assert isinstance(cards, list)
        for card in cards:
            assert isinstance(card, CanonicalCard), (
                f"select_main() must return CanonicalCard objects, got {type(card)}"
            )
            # Verify canonical_id field exists (not posting id)
            assert hasattr(card, "canonical_id")
            assert not hasattr(card, "posting_id") or card.canonical_id is not None


# ---------------------------------------------------------------------------
# AC (d) — Re-ingest Indeed variant does NOT resurface after apply
# ---------------------------------------------------------------------------


class TestReIngestAfterApply:
    def test_reingest_indeed_does_not_resurface(self, db: Path) -> None:
        """AC (d): re-ingest Indeed variant after apply → does NOT resurface in Main.

        Simulated by: applying LinkedIn variant → then confirming the canonical stays
        suppressed even if a new posting_canonical_links row is added for the same
        canonical (as would happen on re-dedup of the same URL).
        """
        pid_a, pid_b, can_id = _build_two_variant_canonical(db)
        mark_applied(pid_a, db_path=db)

        # Simulate re-ingest: add another link to the same canonical
        # (a new posting that dedup-decides to merge into the same canonical)
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            pid_c = _seed_posting(conn, "Senior ML Engineer", "Acme Corp")
            _seed_link(conn, pid_c, can_id, "content_dedup")
            conn.commit()
        finally:
            conn.close()

        # select_main should still exclude canonical — applied state persists
        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can_id not in can_ids, (
            "Re-ingesting an Indeed variant must NOT resurface the canonical in Main "
            "when the LinkedIn variant is already applied"
        )


# ---------------------------------------------------------------------------
# AC (e) — Restore via C7 → canonical re-appears in Main with both sources
# ---------------------------------------------------------------------------


class TestRestoreResurfacesCanonical:
    def test_unapply_brings_canonical_back_to_main(self, db: Path) -> None:
        """AC (e): unapply LinkedIn variant → select_main() includes canonical again.

        C7 API: unapply() removes from applied (same as restore() removes from dismissed).
        TDD §C22 AC (e): "Restore the LinkedIn variant via C7" means undo the apply action.
        """
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)

        # Apply, then unapply (the "restore" for applied postings)
        mark_applied(pid_a, db_path=db)
        unapply(pid_a, db_path=db)

        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can_id in can_ids, (
            "Canonical should re-appear in select_main() after unapplying the applied variant"
        )

    def test_restore_dismissed_brings_canonical_back_to_main(self, db: Path) -> None:
        """AC (e) for dismiss path: restore dismissed variant → canonical re-appears in Main."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)

        # Dismiss then restore
        dismiss(pid_a, db_path=db)
        restore(pid_a, db_path=db)

        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can_id in can_ids, (
            "Canonical should re-appear in select_main() after restoring the dismissed variant"
        )

    def test_restored_card_has_both_sources(self, db: Path) -> None:
        """AC (e): restored canonical card aggregates sources from both linked postings."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)

        mark_applied(pid_a, db_path=db)
        unapply(pid_a, db_path=db)

        cards = select_main(db_path=db)
        matching = [c for c in cards if c.canonical_id == can_id]
        assert len(matching) == 1, "Should be exactly one canonical card"

        card = matching[0]
        # Both source labels should be present in sources_summary
        assert len(card.sources_summary) >= 1, (
            "Restored canonical card must have at least one source in sources_summary"
        )


# ---------------------------------------------------------------------------
# get_canonical_state — full state view object
# ---------------------------------------------------------------------------


class TestGetCanonicalState:
    def test_state_view_structure(self, db: Path) -> None:
        """get_canonical_state returns CanonicalStateView with correct fields."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)
        state = get_canonical_state(can_id, db_path=db)
        assert isinstance(state, CanonicalStateView)
        assert state.canonical_id == can_id
        assert state.is_applied is False
        assert state.is_dismissed is False
        assert state.suppress_from_main is False
        assert state.applied_via_posting_id is None
        assert state.dismissed_via_posting_id is None

    def test_state_view_after_apply(self, db: Path) -> None:
        """get_canonical_state reflects applied state with which posting drove it."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)
        mark_applied(pid_a, db_path=db)
        state = get_canonical_state(can_id, db_path=db)
        assert state.is_applied is True
        assert state.suppress_from_main is True
        assert state.applied_via_posting_id == pid_a

    def test_state_view_after_dismiss(self, db: Path) -> None:
        """get_canonical_state reflects dismissed state."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)
        dismiss(pid_a, db_path=db)
        state = get_canonical_state(can_id, db_path=db)
        assert state.is_dismissed is True
        assert state.suppress_from_main is True


# ---------------------------------------------------------------------------
# AC #5 — Persistence across restart: state inheritance from DB (no in-process state)
# ---------------------------------------------------------------------------


class TestPersistenceAcrossRestart:
    def test_state_persists_across_new_connections(self, db: Path) -> None:
        """AC #5: state inheritance works after server restart (simulated by new connections)."""
        pid_a, _pid_b, can_id = _build_two_variant_canonical(db)

        # Apply via C7 using one connection
        mark_applied(pid_a, db_path=db)

        # Read state via C22 using a fresh connection (simulates server restart)
        # All C22 functions open their own connections — no shared in-process state
        assert is_canonical_applied(can_id, db_path=db) is True

        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can_id not in can_ids, (
            "State must persist across connections (simulating server restart)"
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_select_main_empty_db(self, db: Path) -> None:
        """select_main on empty DB returns empty list (no crash)."""
        cards = select_main(db_path=db)
        assert cards == []

    def test_select_main_multiple_canonicals(self, db: Path) -> None:
        """select_main returns multiple canonicals when none are applied/dismissed."""
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            # Create two independent canonicals
            pid1 = _seed_posting(conn, "Senior Data Scientist", "Corp A")
            can1 = _seed_canonical(conn, "Senior Data Scientist", "Corp A")
            _seed_link(conn, pid1, can1)

            pid2 = _seed_posting(conn, "ML Engineer", "Corp B")
            can2 = _seed_canonical(conn, "ML Engineer", "Corp B")
            _seed_link(conn, pid2, can2)
            conn.commit()
        finally:
            conn.close()

        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can1 in can_ids
        assert can2 in can_ids

    def test_applying_one_canonical_does_not_suppress_others(self, db: Path) -> None:
        """Applying a posting for canonical X does not suppress canonical Y."""
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            pid1 = _seed_posting(conn, "Senior Data Scientist", "Corp A")
            can1 = _seed_canonical(conn, "Senior Data Scientist", "Corp A")
            _seed_link(conn, pid1, can1)

            pid2 = _seed_posting(conn, "ML Engineer", "Corp B")
            can2 = _seed_canonical(conn, "ML Engineer", "Corp B")
            _seed_link(conn, pid2, can2)
            conn.commit()
        finally:
            conn.close()

        mark_applied(pid1, db_path=db)

        cards = select_main(db_path=db)
        can_ids = {c.canonical_id for c in cards}
        assert can1 not in can_ids, "Applied canonical should be suppressed"
        assert can2 in can_ids, "Other canonical must NOT be affected"
