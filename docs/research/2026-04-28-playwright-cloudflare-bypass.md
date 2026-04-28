# Browser-Based Cloudflare Bypass — Research Brief
**Date**: 2026-04-28
**Scope**: Playwright/Chromium approach selection for `browser_fetcher.py` fallback in jd-matcher

---

## Context

Indeed.com is 100% blocked at the IP/TLS level by Cloudflare as of 2026-04-27. All `requests`-based
approaches and `curl_cffi` impersonation have failed. This brief evaluates browser-automation options
for a `browser_fetcher.py` module that any hydrator can fall back to on 403.

---

## Recommendation

**Primary: `patchright` in headed mode (`headless=False`) with a persistent user-data directory.**

Patchright is an actively-maintained (v1.58.2, released 2026-03-07), drop-in Playwright replacement
that patches the CDP `Runtime.enable` leak — the exact signal Cloudflare has weaponised since early
2025. Running headed with a persistent profile gives Chromium a real browser fingerprint. At 5–15
requests/day with 30 s jitter, IP-level block risk is low. Headed mode on macOS requires no extra
infrastructure (no Xvfb). The Playwright-identical API means data-pipeline integration is trivial.

**Fallback: `nodriver` (v0.48.1, 2025-11-09).** Different paradigm (async-only, no Playwright API),
but purpose-built for Cloudflare bypass with minimal CDP footprint. Drop to this if patchright stops
working.

**Do NOT use**: vanilla `playwright` (immediate Runtime.enable detection), `playwright-stealth`
(proof-of-concept quality, no guarantee on Cloudflare challenge mode), `camoufox` (maintainer stepped
down January 2026, Clover Labs fork is experimental).

---

## Comparison Table

| Approach | Cloudflare challenge bypass | Maturity (April 2026) | Footprint | Maintenance | Verdict |
|---|---|---|---|---|---|
| Vanilla `playwright` headless | Fails — Runtime.enable detected immediately | Stable | 706 MB | Excellent (MS) | Reject |
| `playwright-stealth` Python (v2.0.3) | Partial — fingerprint evasion only; does NOT cover CDP or TLS layer | Proof-of-concept | +0 MB | Active (Apr 2026) | Reject for CF |
| `patchright` (v1.58.2) headed | Moderate-to-high; patches Runtime.enable; headless ~35% success, headed higher; CF claims "✅" in README | Drop-in Playwright replacement | ~1 GB headed | Active (Mar 2026, 1.3k stars) | **Primary pick** |
| `camoufox` Firefox-based | Was "0% headless detection" benchmark; maintenance gap Jan 2025–Jan 2026; highly experimental now | Experimental (Clover Labs fork) | ~800 MB | Uncertain | Reject (for now) |
| `nodriver` (v0.48.1) | High — no WebDriver component at all; no Runtime.enable; async Chrome CDP direct | Stable but async-only | ~700 MB | Active (Nov 2025) | Fallback |
| SeleniumBase UC/CDP mode | High — reportedly 100% on Indeed in one 2025-26 report; uses PyAutoGUI mouse sim | Stable, well-documented | ~400 MB | Excellent | Alternative if patchright fails |
| CDP-attach existing Chrome | Highest theoretical — real user Chrome, real cookies; Cloudflare cannot distinguish | No install needed | 0 MB extra | N/A (user infra) | Last-resort fallback |

---

## Key Technical Facts Per Question

### Q1: Cloudflare bypass state of the art (2026)

The Cloudflare challenge stack in 2026 operates at four layers simultaneously:
1. **TLS/JA4+ fingerprint** — matches claimed UA against real browser TLS signature
2. **CDP Runtime.enable leak** — fired by vanilla Playwright, Selenium; detected since Feb 2025
3. **Chrome mouse-click coordinate bug** — CDP clicks expose `screenX/Y` inconsistency vs iframe; Google patch merged Sep 2025 but merge status into stable Chrome unknown
4. **Behavioral signals** — scroll timing, interaction patterns, headless-specific JS markers (`navigator.webdriver`, missing audio/video codecs)

`patchright` addresses layers 2 and 4 (CDP patch + JS isolation). It does NOT independently solve layer 1 (TLS) or the coordinate bug (layer 3), but a real headed Chromium installation closely matches the TLS signature of a real browser. With headed mode the coordinate bug is moot (real OS mouse events are used).

`playwright-stealth` (Python) is v2.0.3 and actively maintained, but its README explicitly says "proof-of-concept" — it covers only JS fingerprints (layer 4 surface), not CDP leak or TLS.

`nodriver` skips the CDP Runtime.enable call entirely (no WebDriver protocol), making it structurally cleaner than patchright. Scrapfly's 2026 guide ranks it as "Recommended". Limitation: async-only, no sync API, no Playwright page model.

`camoufox` theoretically achieves "0% headless detection" via C++ Firefox hooks, but it went through a 12-month maintenance gap (Jan 2025 – Jan 2026), and the current Clover Labs fork is explicitly "highly experimental." No production recommendation until it stabilises.

Indeed-specific: one 2025-26 report achieved 100% success on Indeed with SeleniumBase UC mode + CDP + PyAutoGUI click simulation. No patchright-specific Indeed reports found, but Indeed uses standard Cloudflare challenge (not DataDome or Turnstile-heavy), which patchright targets.

### Q2: Headless detection — is it really an issue?

Yes, headless detection is real and significant in 2026:

- **`navigator.webdriver`**: trivially detectable; both patchright and playwright-stealth patch this
- **Missing audio/video codecs**: headless Chromium lacks many codecs real Chrome has; detectable via JS
- **CDP coordinate bug**: headless mode exposes `screenX/Y` < 100px on click; Google patch unmerged as of Oct 2025
- **HeadlessChrome UA string**: headless Chromium sends `HeadlessChrome` in UA by default; patchright should suppress but this is a known leak point per the roundproxies benchmark
- **Benchmark result**: patchright headless achieves ~35% bypass success across 20 tested CF-protected domains. Headed mode is significantly better but no hard number found.

**Bottom line**: for a personal-use tool on macOS with a display available, `headless=False` is the correct default. The window can be minimised. No Xvfb needed on macOS.

### Q3: CDP-attach to existing Chrome

```python
# Launch Chrome manually with:
# /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]  # reuse existing context
    page = await context.new_page()
    await page.goto(url)
    html = await page.content()
```

**Key gotchas**:
- Chrome must be launched with `--remote-debugging-port=9222` BEFORE the script runs; cannot attach to a running Chrome that was not started with this flag (Chrome M144+ adds a workaround but Playwright does not support that path yet per issue #40027)
- `browser.contexts[0]` reuses the user's real session including cf_clearance cookies — this is the main benefit
- Tabs from the user's real session are visible; script-opened tabs are visible to user — minor UX nuisance, not a blocker
- Cookie isolation: none — the script can read/write the user's actual cookies
- Security: any JS executing in the page has full access to user's session; only matters if you're loading untrusted third-party content (job description HTML is relatively safe)
- Cloudflare detection: Cloudflare cannot distinguish this from a human-driven Chrome tab. This is the strongest bypass option IF the user keeps Chrome running with the debug port open.

### Q4: Performance and footprint

| Metric | Value | Source |
|---|---|---|
| Headless Chromium memory (single tab) | ~706 MB peak | datawookie.dev benchmark 2025 |
| Headed Chromium memory (single tab) | ~1,094 MB peak | datawookie.dev benchmark 2025 |
| Chromium download (playwright install) | ~300 MB | standard Playwright chromium |
| Per-page overhead (load → DOM ready) | 5–7 s for Indeed-scale pages | SeleniumBase report |
| SeleniumBase UC mode memory | 200–400 MB | roundproxies estimate |

**Lifecycle recommendation**: singleton browser (launch once, reuse across requests), new tab per request, close tab after HTML extraction. At 5–15 requests/day there is no reason to launch/kill per request — startup cost is ~2–3 s and memory cost is not recovered between short requests.

### Q5: Maintenance fragility

- `patchright` tracks Playwright releases automatically with the same version number. A new Playwright release generally triggers a new patchright release within days. Community project risk: one maintainer (Vinyzu); 1.3k GitHub stars; active as of March 2026.
- `playwright-stealth` (Python) v2.0.3 released April 2026 — actively maintained, but as noted it does not solve the CF challenge layer, so maintenance frequency is not the binding constraint.
- `camoufox` — do not use until Clover Labs fork stabilises and issues a non-experimental release.
- `nodriver` — last release November 2025. Maintenance status is "healthy" per Snyk. Succession to undetected-chromedriver with same author. Main risk: async-only API requires different code patterns.
- **Dead libraries to avoid**: `undetected-chromedriver` (superseded by nodriver), `cloudscraper` (requests-based, no browser; does not survive 2025 CF JS challenges), FlareSolverr (relies on undetected-chromedriver which is superseded).

---

## Implementation Sketch

```python
# browser_fetcher.py — pseudocode for patchright singleton

from patchright.async_api import async_playwright, Browser
import asyncio, logging
from pathlib import Path

_browser: Browser | None = None
USER_DATA_DIR = Path.home() / ".jd_matcher" / "chrome_profile"

async def _get_browser() -> Browser:
    """Singleton: launch once, reuse across calls."""
    global _browser
    if _browser is None or not _browser.is_connected():
        playwright = await async_playwright().start()
        _browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,        # critical: headed avoids ~65% detection rate hit
            no_viewport=True,      # patchright README recommendation
            args=["--start-minimized"],
        )
        logging.info("patchright browser launched (headed, persistent context)")
    return _browser


async def fetch_html(url: str, timeout: int = 30) -> bytes | None:
    """
    Fetch HTML via patchright browser. Returns raw bytes or None on failure.
    Caller is responsible for rate-limit jitter before calling.
    """
    context = await _get_browser()
    page = await context.new_page()
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if response is None or response.status >= 400:
            logging.warning("fetch_html: HTTP %s for %s", response.status if response else "None", url)
            return None
        # Detect CF challenge page
        content = await page.content()
        if "cf-challenge" in content or "Checking your browser" in content:
            logging.warning("fetch_html: Cloudflare challenge page returned for %s", url)
            return None
        return content.encode("utf-8")
    except Exception as exc:
        logging.error("fetch_html error for %s: %s", url, exc)
        return None
    finally:
        await page.close()


# indeed.py integration point:
# if response.status_code in (403, 429) or "cf-mitigated" in response.headers:
#     html = asyncio.run(fetch_html(url))
#     if html:
#         return _parse_jd(html)
```

**Notes for data-pipeline**:
- `launch_persistent_context` returns a `BrowserContext`, not a `Browser`. Adapt accordingly — new_page() is called on the context directly.
- `patchright` install: `pip install patchright && python -m patchright install chromium`
- For sync indeed.py code: wrap `asyncio.run(fetch_html(...))` or move to async throughout

---

## Open Questions for the User

1. **Headed mode visibility**: `patchright` in headed mode will briefly open (and minimise) a Chromium window when the browser first launches. Is this acceptable on your machine, or would you prefer a stricter "invisible" requirement that forces the CDP-attach fallback?

2. **CDP-attach as named fallback tier**: If headed patchright still fails on Indeed (possible — Cloudflare may be doing IP-level blocking that no browser can defeat without a proxy), the strongest free fallback is to attach to your actual Chrome with `--remote-debugging-port=9222`. This requires you to keep Chrome running with that flag. Should we build this as a second fallback tier, or only consider it if patchright fails in practice?

3. **Proxy**: You ruled out paid services. Are you open to a free residential proxy (e.g., through a VPN tool's SOCKS5 proxy) as an extra layer if patchright headed still gets blocked? This is the one lever left after browser stealth is maximised.

---

## Risks

**Risk 1 — Cloudflare may be doing IP-level enforcement (severity: HIGH)**
The user confirmed the challenge appears on the homepage, viewjob, and search. This is consistent with IP-level blocking, not just fingerprint detection. If Indeed has flagged the user's home IP as suspicious (e.g., prior scraping attempts), even a headed real Chrome from the same IP will hit the challenge. Browser stealth won't help. Mitigation: the CDP-attach fallback (real Chrome session with existing cf_clearance) is the only countermeasure that doesn't require a proxy.

**Risk 2 — Maintenance treadmill for patchright (severity: MEDIUM)**
Cloudflare actively reverse-engineers open-source tools. Patchright is a one-person project. A new Cloudflare detection signal could break patchright between Playwright releases, leaving a window of days to weeks where the tool is broken. Mitigation: pin patchright version in requirements.txt, test on every Indeed hydration run, have nodriver as a coded (but inactive) fallback branch.

**Risk 3 — Headed-mode footprint on user's machine (severity: LOW)**
~1 GB RAM for a headed Chromium instance is non-trivial on a laptop. Singleton pattern means this cost is paid once per session (not per request), but it will be visible in Activity Monitor. Mitigation: singleton teardown on idle (close browser after N minutes of no requests); or switch to headless if patchright improves headless stealth in a future release.
