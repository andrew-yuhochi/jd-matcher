/**
 * jd-matcher frontend — M1 keyboard handler + events instrumentation (C9 / C10)
 *
 * Invariants:
 *   - Session ID generated once per page load via crypto.randomUUID()
 *   - Every emitEvent() call is fire-and-forget (best-effort: failures never block UI)
 *   - Source-health badges have NO dismiss/close affordance in JS (non-hideable rule)
 *   - `d`/`a`/`o` work on hydration-failed cards (never blocked by hydration_status)
 */

"use strict";

// ---------------------------------------------------------------------------
// Session ID
// ---------------------------------------------------------------------------

function getSessionId() {
  let sid = sessionStorage.getItem("jdm_session_id");
  if (!sid) {
    sid = crypto.randomUUID();
    sessionStorage.setItem("jdm_session_id", sid);
  }
  return sid;
}

const SESSION_ID = getSessionId();

// ---------------------------------------------------------------------------
// Events instrumentation (C10 — best-effort)
// ---------------------------------------------------------------------------

function emitEvent(type, postingId, metadata) {
  fetch("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_type: type,
      posting_id: postingId || null,
      metadata: metadata || null,
      session_id: SESSION_ID,
    }),
  }).catch(function () {
    /* drop silently — best-effort per TDD §C10 */
  });
}

// ---------------------------------------------------------------------------
// Card view tracking (IntersectionObserver)
// ---------------------------------------------------------------------------

// Maps posting_id -> timestamp when the card first became visible
const cardViewTimes = {};

function setupIntersectionObserver() {
  if (!("IntersectionObserver" in window)) return;

  const observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        const card = entry.target;
        const pid = parseInt(card.dataset.postingId, 10);
        if (!pid || cardViewTimes[pid]) return; // already recorded
        cardViewTimes[pid] = Date.now();
        emitEvent("card_viewed", pid, null);
      });
    },
    { threshold: 0.5 }
  );

  document.querySelectorAll(".card[data-posting-id]").forEach(function (card) {
    observer.observe(card);
  });
}

// ---------------------------------------------------------------------------
// Card focus management
// ---------------------------------------------------------------------------

let focusedCard = null;

function getCards() {
  // Only cards in the current visible list (excludes hidden ones)
  return Array.from(
    document.querySelectorAll(".card[data-posting-id]:not(.dismissing):not(.applying)")
  );
}

function setFocused(card) {
  if (focusedCard && focusedCard !== card) {
    focusedCard.classList.remove("card-focused");
  }
  focusedCard = card;
  if (card) {
    card.classList.add("card-focused");
    card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function moveFocus(direction) {
  const cards = getCards();
  if (!cards.length) return;

  if (!focusedCard || !cards.includes(focusedCard)) {
    setFocused(cards[direction === 1 ? 0 : cards.length - 1]);
    return;
  }

  const idx = cards.indexOf(focusedCard);
  const next = cards[idx + direction];
  if (next) setFocused(next);
}

// ---------------------------------------------------------------------------
// Cheatsheet modal
// ---------------------------------------------------------------------------

const cheatsheet = document.getElementById("cheatsheet");

function openCheatsheet() {
  cheatsheet.classList.add("open");
}

function closeCheatsheet() {
  cheatsheet.classList.remove("open");
}

function isCheatsheetOpen() {
  return cheatsheet.classList.contains("open");
}

// Close cheatsheet on backdrop click
cheatsheet.addEventListener("click", function (e) {
  if (e.target === cheatsheet) closeCheatsheet();
});

// ---------------------------------------------------------------------------
// Source-health badge update
// ---------------------------------------------------------------------------

const SOURCE_LABELS = {
  gmail_linkedin: "LI-email",
  gmail_indeed: "IN-email",
  hydrator_linkedin: "LI-hydrate",
  hydrator_indeed: "IN-hydrate",
};

function updateBadge(entry) {
  const el = document.getElementById("badge-" + entry.source);
  if (!el) return;

  // Remove all status classes and re-apply
  el.classList.remove("badge-healthy", "badge-degraded", "badge-failed", "badge-never_run");
  el.classList.add("badge-" + entry.health_status);

  // Tooltip: show failure reason if present, otherwise last-run info
  let tooltip = "";
  if (entry.failure_reason) {
    tooltip = entry.failure_reason;
    if (entry.last_successful_fetch_at) {
      tooltip += " | Last OK: " + entry.last_successful_fetch_at.slice(0, 10);
    }
  } else if (entry.last_run) {
    tooltip = "Last run: " + entry.last_run.slice(0, 10);
  }
  el.title = tooltip;
  // NO close button added — non-hideable invariant
}

function fetchSourceHealth() {
  fetch("/api/source-health")
    .then(function (r) { return r.json(); })
    .then(function (entries) {
      entries.forEach(updateBadge);
    })
    .catch(function () { /* silent */ });
}

// ---------------------------------------------------------------------------
// Sync button
// ---------------------------------------------------------------------------

const btnSync = document.getElementById("btn-sync");
if (btnSync) {
  btnSync.addEventListener("click", function () {
    const pid = focusedCard ? parseInt(focusedCard.dataset.postingId, 10) : null;
    emitEvent("sync_triggered", pid, null);
    btnSync.disabled = true;
    btnSync.textContent = "Syncing…";

    fetch("/sync", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        emitEvent("sync_completed", null, {
          run_id: data.run_id,
          total_new_postings: data.total_new_postings,
        });
        fetchSourceHealth();
        // Reload to surface new postings
        window.location.reload();
      })
      .catch(function () {
        btnSync.disabled = false;
        btnSync.textContent = "Run sync now";
      });
  });
}

// ---------------------------------------------------------------------------
// Dismiss (d)
// ---------------------------------------------------------------------------

function dismissCard(card) {
  const pid = parseInt(card.dataset.postingId, 10);
  const viewedAt = cardViewTimes[pid];
  const timeToDecideMs = viewedAt ? Date.now() - viewedAt : null;

  card.classList.add("dismissing");

  setTimeout(function () {
    // Collapse (height → 0) after slide-left finishes
    card.style.height = card.offsetHeight + "px";
    card.style.overflow = "hidden";
    // Force reflow so transition applies
    card.offsetHeight; // eslint-disable-line no-unused-expressions
    card.style.transition = "height 100ms ease-in, padding 100ms ease-in, margin 100ms ease-in";
    card.style.height = "0";
    card.style.paddingTop = "0";
    card.style.paddingBottom = "0";
    card.style.marginBottom = "0";

    setTimeout(function () {
      card.remove();
      moveFocus(1);
    }, 100);
  }, 180);

  emitEvent("card_dismissed", pid, {
    time_to_decide_ms: timeToDecideMs,
    session_id: SESSION_ID,
  });

  fetch("/postings/" + pid + "/dismiss", { method: "POST" }).catch(function () {});
}

// ---------------------------------------------------------------------------
// Apply (a)
// ---------------------------------------------------------------------------

function applyCard(card) {
  const pid = parseInt(card.dataset.postingId, 10);
  const viewedAt = cardViewTimes[pid];
  const timeToDecideMs = viewedAt ? Date.now() - viewedAt : null;

  card.classList.add("applying");

  setTimeout(function () {
    card.remove();
    moveFocus(1);
  }, 150);

  emitEvent("card_marked_applied", pid, {
    time_to_decide_ms: timeToDecideMs,
    session_id: SESSION_ID,
  });

  fetch("/postings/" + pid + "/apply", { method: "POST" }).catch(function () {});
}

// ---------------------------------------------------------------------------
// Restore button (Dismissed tab)
// ---------------------------------------------------------------------------

document.querySelectorAll(".btn-restore").forEach(function (btn) {
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    const pid = parseInt(btn.dataset.postingId, 10);
    emitEvent("card_restored", pid, null);
    fetch("/postings/" + pid + "/restore", { method: "POST" })
      .then(function () {
        const card = document.getElementById("card-" + pid);
        if (card) card.remove();
      })
      .catch(function () {});
  });
});

// ---------------------------------------------------------------------------
// Unapply button (Applied tab)
// ---------------------------------------------------------------------------

document.querySelectorAll(".btn-unapply").forEach(function (btn) {
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
    const pid = parseInt(btn.dataset.postingId, 10);
    emitEvent("card_restored", pid, null);
    fetch("/postings/" + pid + "/unapply", { method: "POST" })
      .then(function () {
        const card = document.getElementById("card-" + pid);
        if (card) card.remove();
      })
      .catch(function () {});
  });
});

// ---------------------------------------------------------------------------
// Click-to-select cards (event delegation per list container)
// ---------------------------------------------------------------------------

// Action button selectors that must NOT trigger card select/expand
const ACTION_BUTTON_SELECTORS = ".btn-apply, .btn-dismiss, .btn-restore, .btn-unapply, .card-apply-link";

function handleCardContainerClick(e) {
  const card = e.target.closest(".card[data-posting-id]");
  if (!card) return;

  // Don't fire when clicking action buttons or links
  if (e.target.closest(ACTION_BUTTON_SELECTORS)) return;

  setFocused(card);

  // Clicking card body (non-button area) also expands the card
  const expanded = card.classList.toggle("expanded");
  card.classList.add("card-viewed");
  const pid = parseInt(card.dataset.postingId, 10);
  emitEvent("card_expanded", pid, { expanded: expanded });
}

[".postings-list", ".applied-list", ".dismissed-list"].forEach(function (sel) {
  const container = document.querySelector(sel);
  if (container) container.addEventListener("click", handleCardContainerClick);
});

// Stop propagation on apply/dismiss buttons so parent card click doesn't also fire
document.querySelectorAll(".btn-apply, .btn-dismiss").forEach(function (btn) {
  btn.addEventListener("click", function (e) {
    e.stopPropagation();
  });
});

// ---------------------------------------------------------------------------
// Keyboard handler
// ---------------------------------------------------------------------------

const isDismissedTab = document.querySelector(".tab.active[data-tab='dismissed']") !== null;

document.addEventListener("keydown", function (e) {
  // Ignore shortcuts when focus is on an input/textarea/select
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") {
    if (e.key === "Escape") e.target.blur();
    return;
  }

  switch (e.key) {
    case "j":
    case "ArrowDown":
      e.preventDefault();
      moveFocus(1);
      break;

    case "k":
    case "ArrowUp":
      e.preventDefault();
      moveFocus(-1);
      break;

    case "e":
      if (focusedCard) {
        const expanded = focusedCard.classList.toggle("expanded");
        focusedCard.classList.add("card-viewed");
        const pid = parseInt(focusedCard.dataset.postingId, 10);
        emitEvent("card_expanded", pid, { expanded: expanded });
      }
      break;

    case "d":
      if (focusedCard && !isDismissedTab) {
        dismissCard(focusedCard);
      }
      break;

    case "a":
      if (focusedCard && !isDismissedTab) {
        applyCard(focusedCard);
      }
      break;

    case "o":
      if (focusedCard) {
        // Open first source URL (LinkedIn precedence — first link in DOM order)
        const firstLink = focusedCard.querySelector(".card-apply-link");
        if (firstLink) window.open(firstLink.href, "_blank", "noopener,noreferrer");
        // no-op if no URL present
      }
      break;

    case "O":
      if (focusedCard) {
        // Open ALL source URLs in new tabs
        const allLinks = focusedCard.querySelectorAll(".card-apply-link");
        allLinks.forEach(function (link) {
          window.open(link.href, "_blank", "noopener,noreferrer");
        });
      }
      break;

    case "c":
      // No-op pre-M4 per UX-SPEC §6
      break;

    case "1":
      emitEvent("tab_switched", null, { tab: "main" });
      window.location.href = "/";
      break;

    case "2":
      emitEvent("tab_switched", null, { tab: "applied" });
      window.location.href = "/applied";
      break;

    case "3":
      emitEvent("tab_switched", null, { tab: "dismissed" });
      window.location.href = "/dismissed";
      break;

    case "/":
      e.preventDefault();
      const searchInput = document.getElementById("dismissed-search");
      if (searchInput) searchInput.focus();
      break;

    case "?":
      openCheatsheet();
      break;

    case "Escape":
      if (isCheatsheetOpen()) {
        closeCheatsheet();
      } else if (focusedCard && focusedCard.classList.contains("expanded")) {
        focusedCard.classList.remove("expanded");
      }
      break;

    default:
      break;
  }
});

// ---------------------------------------------------------------------------
// Dismissed-tab search filter
// ---------------------------------------------------------------------------

const dismissedSearch = document.getElementById("dismissed-search");
if (dismissedSearch) {
  dismissedSearch.addEventListener("input", function () {
    const q = dismissedSearch.value.toLowerCase();
    document.querySelectorAll(".card-dismissed").forEach(function (card) {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(q) ? "" : "none";
    });
  });
}

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------

emitEvent("session_start", null, null);
setupIntersectionObserver();
fetchSourceHealth();

// session_end on page unload (best-effort — browser may not deliver)
window.addEventListener("beforeunload", function () {
  emitEvent("session_end", null, null);
});
