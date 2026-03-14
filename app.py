import streamlit as st
import pandas as pd
import asyncio
import subprocess
import sys
import re
import traceback
from unidecode import unidecode

# ── Install Playwright + stealth patch ───────────────────────────────────────
@st.cache_resource(show_spinner="Installing Chromium (first run only) …")
def _install_playwright():
    r1 = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True,
    )
    # Also install playwright-stealth to bypass bot detection
    r2 = subprocess.run(
        [sys.executable, "-m", "pip", "install", "playwright-stealth", "--quiet"],
        capture_output=True, text=True,
    )
    code = r1.returncode or r2.returncode
    return code, r1.stdout + r2.stdout, r1.stderr + r2.stderr

_pw_code, _pw_out, _pw_err = _install_playwright()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Betrail Score Scraper", page_icon="🏃", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Space Mono', monospace; }
.stApp { background: #0d0d0d; color: #e8e8e8; }
.block-container { padding-top: 2rem; max-width: 1100px; }
.title-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 0.25rem; }
.badge { background: #00e5a0; color: #000; font-family: 'Space Mono', monospace;
    font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 3px;
    letter-spacing: 0.08em; text-transform: uppercase; vertical-align: middle; }
.metric-box { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 1rem 1.5rem; text-align: center; }
.metric-num { font-family: 'Space Mono', monospace; font-size: 2rem; font-weight: 700; color: #00e5a0; }
.metric-lbl { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 0.08em; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔧 System status")
    if _pw_code != 0:
        st.error(f"Install failed (exit {_pw_code})")
        with st.expander("Log"): st.code(_pw_out); st.code(_pw_err)
    else:
        st.success("✅ Chromium + stealth ready")

    st.markdown("---")
    st.markdown("### 🔗 URL preview")
    t_last  = st.text_input("Lastname",  "CHAVENT", key="diag_last")
    t_first = st.text_input("Firstname", "Pascal",  key="diag_first")

    def _slug(text):
        return re.sub(r"[^a-z0-9]+", "", unidecode(str(text)).lower().strip())

    preview_url = f"https://www.betrail.run/runner/{_slug(t_last)}.{_slug(t_first)}/overview"
    st.code(preview_url, language=None)

    if st.button("🔍 Debug scrape this runner", use_container_width=True):
        with st.spinner("Scraping …"):
            import tempfile, os
            debug_script = """
import asyncio, re, sys
from playwright.async_api import async_playwright
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

XPATH = (
    "/html/body/app-root/div/div/div/runner-page/div/div/"
    "app-runner-overview/div/div[1]/div/bt-card[1]/div/div[3]/"
    "div[1]/div/runner-level/div/runner-score/div"
)

import sys
URL = sys.argv[1]

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-dev-shm-usage","--disable-gpu",
                  "--single-process","--no-zygote"]
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="fr-FR",
            extra_http_headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        page = await ctx.new_page()
        if HAS_STEALTH:
            await stealth_async(page)
            print("STEALTH: enabled")
        else:
            print("STEALTH: not available")

        resp = await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        print("STATUS:", resp.status if resp else "None")
        print("URL:", page.url)
        print("TITLE:", await page.title())

        if resp and resp.status == 200:
            try:
                await page.wait_for_selector("runner-score", timeout=15000)
                print("runner-score element: FOUND")
            except Exception:
                print("runner-score element: NOT FOUND within 15s")

            try:
                loc = page.locator("xpath=" + XPATH)
                await loc.wait_for(timeout=8000)
                print("SCORE_XPATH:", (await loc.inner_text()).strip())
            except Exception as e:
                print("XPATH_FAIL:", e)

            try:
                locs = page.locator("runner-score div")
                n = await locs.count()
                print("CSS runner-score div count:", n)
                for i in range(min(n, 5)):
                    txt = (await locs.nth(i).inner_text()).strip()
                    print("  [" + str(i) + "]:", txt)
            except Exception as e:
                print("CSS_FAIL:", e)

        await browser.close()

asyncio.run(run())
"""
            # Write to a temp file to avoid f-string escaping issues
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                             delete=False) as tf:
                tf.write(debug_script)
                tmp_path = tf.name
            try:
                dbg = subprocess.run(
                    [sys.executable, tmp_path, preview_url],
                    capture_output=True, text=True, timeout=90
                )
            finally:
                os.unlink(tmp_path)

        st.markdown("**Debug output:**")
        st.code(dbg.stdout or "(no stdout)")
        if dbg.stderr:
            st.code(dbg.stderr)

# ── Core helpers ──────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unidecode(str(text)).lower().strip())

def build_url(lastname: str, firstname: str) -> str:
    return f"https://www.betrail.run/runner/{slugify(lastname)}.{slugify(firstname)}/overview"

XPATH = (
    "/html/body/app-root/div/div/div/runner-page/div/div/"
    "app-runner-overview/div/div[1]/div/bt-card[1]/div/div[3]/"
    "div[1]/div/runner-level/div/runner-score/div"
)

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-dev-shm-usage", "--disable-gpu",
    "--single-process", "--no-zygote",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

async def make_context(browser):
    """Create a browser context that looks like a real browser."""
    return await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800},
        locale="fr-FR",
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
        },
    )

async def scrape_one(url: str, browser) -> str:
    try:
        from playwright_stealth import stealth_async
        has_stealth = True
    except ImportError:
        has_stealth = False

    ctx = await make_context(browser)
    page = await ctx.new_page()
    try:
        if has_stealth:
            await stealth_async(page)

        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        if resp is None:
            return "error: no response"
        if resp.status == 403:
            return "error: 403 blocked"
        if resp.status == 404:
            return "not found"
        if resp.status >= 400:
            return f"error: HTTP {resp.status}"

        # Wait for Angular to render the score component
        try:
            await page.wait_for_selector("runner-score", timeout=15_000)
        except Exception:
            return "not found"

        # Try XPath first
        try:
            loc = page.locator(f"xpath={XPATH}")
            await loc.wait_for(timeout=8_000)
            text = (await loc.inner_text()).strip()
            m = re.search(r"[\d,.]+", text)
            return m.group(0) if m else text
        except Exception:
            pass

        # CSS fallback
        try:
            loc2 = page.locator("runner-score div").first
            await loc2.wait_for(timeout=5_000)
            text = (await loc2.inner_text()).strip()
            m = re.search(r"[\d,.]+", text)
            return m.group(0) if m else (text or "not found")
        except Exception:
            return "not found"

    except Exception as e:
        return f"error: {type(e).__name__}: {str(e)[:80]}"
    finally:
        await ctx.close()


async def scrape_all(rows: list, progress_cb, log_cb) -> list:
    from playwright.async_api import async_playwright
    MAX_CONCURRENT = 2
    scores = [""] * len(rows)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def task(idx: int, row: dict):
            url = build_url(row["lastname"], row["firstname"])
            async with semaphore:
                score = await scrape_one(url, browser)
            scores[idx] = score
            log_cb(idx, row.get("lastname","?"), row.get("firstname","?"), url, score)
            progress_cb(idx + 1)

        await asyncio.gather(*[task(i, r) for i, r in enumerate(rows)])
        await browser.close()
    return scores


def run_scraper(rows, progress_cb, log_cb):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, scrape_all(rows, progress_cb, log_cb))
        try:
            return future.result(timeout=600)
        except Exception as e:
            raise RuntimeError(f"{e}\n\n{traceback.format_exc()}") from e


# ── UI ────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="title-bar"><h1 style="margin:0">🏃 Betrail Score Scraper</h1>'
    '<span class="badge">v1.5</span></div>', unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:0.25rem'>Upload a CSV of runners → "
            "fetch their Betrail scores → download enriched CSV.</p>",
            unsafe_allow_html=True)
st.divider()

uploaded = st.file_uploader("Upload your CSV file", type=["csv"],
    help="Required columns: lastname, firstname")

df = None
if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=None, engine="python", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        col_lower = {c.lower(): c for c in df.columns}
        missing = [r for r in ["lastname","firstname"] if r not in col_lower]
        if missing:
            st.error(f"CSV is missing required columns: {', '.join(missing)}")
            df = None
        else:
            df = df.rename(columns={
                col_lower["lastname"]:  "lastname",
                col_lower["firstname"]: "firstname",
            })
            st.success(f"✅ Loaded **{len(df)}** runners.")
            with st.expander("Preview (first 5 rows)", expanded=False):
                st.dataframe(df.head(), use_container_width=True)
    except Exception as e:
        st.error(f"Could not parse CSV: {e}")

if df is not None:
    if st.button("🚀 Start scraping", type="primary", use_container_width=True):
        total = len(df)
        progress_bar = st.progress(0, text="Initialising …")
        status_text  = st.empty()
        log_area     = st.expander("📋 Live scraping log", expanded=True)
        log_lines    = []

        def update_progress(done: int):
            progress_bar.progress(done / total, text=f"Scraping runner {done} / {total} …")
            status_text.markdown(
                f"<small style='color:#888'>Completed: {done}/{total}</small>",
                unsafe_allow_html=True)

        def log_cb(idx, last, first, url, score):
            is_score = score not in ("not found","") and not str(score).startswith("error")
            icon = "✅" if is_score else ("⚠️" if score == "not found" else "❌")
            log_lines.append(f"{icon} **{last} {first}** → `{score}`")
            log_area.markdown("\n\n".join(log_lines))

        rows = df.to_dict(orient="records")
        try:
            scores = run_scraper(rows, update_progress, log_cb)
        except Exception as exc:
            st.error(f"**Scraping failed.**\n\n```\n{exc}\n```")
            st.stop()

        progress_bar.progress(1.0, text="Done ✓")
        status_text.empty()

        result_df = df.copy()
        result_df["betrail_score"] = scores

        found     = sum(1 for s in scores if s not in ("not found","") and not str(s).startswith("error"))
        not_found = sum(1 for s in scores if s == "not found")
        errors    = sum(1 for s in scores if str(s).startswith("error"))

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        for col, num, lbl in [(c1,total,"Total"),(c2,found,"Found"),(c3,not_found,"Not found"),(c4,errors,"Errors")]:
            with col:
                st.markdown(f'<div class="metric-box"><div class="metric-num">{num}</div>'
                            f'<div class="metric-lbl">{lbl}</div></div>', unsafe_allow_html=True)

        st.divider()
        st.subheader("Results")

        display_cols = []
        for c in ["name","bibNumber","competition.reportName","betrail_score"]:
            m = next((col for col in result_df.columns if col.lower() == c.lower()), None)
            if m: display_cols.append(m)
            elif c == "betrail_score": display_cols.append("betrail_score")
        if not display_cols: display_cols = list(result_df.columns)

        def style_score(val):
            v = str(val)
            if v == "not found": return "color:#ff6b6b;font-style:italic"
            if v.startswith("error"): return "color:#ffa94d;font-style:italic"
            return "color:#00e5a0;font-weight:700;font-family:monospace"

        st.dataframe(
            result_df[display_cols].style.map(style_score, subset=["betrail_score"]),
            use_container_width=True, height=420)

        st.divider()
        st.download_button("⬇️ Download enriched CSV",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="runners_with_scores.csv", mime="text/csv",
            type="primary", use_container_width=True)
