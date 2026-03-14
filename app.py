import streamlit as st
import pandas as pd
import asyncio
import subprocess
import sys
import re
import traceback
from unidecode import unidecode

# ── Ensure Playwright browser binary is installed ─────────────────────────────
@st.cache_resource(show_spinner="Installing Chromium (first run only) …")
def _install_playwright():
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr

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
        st.error(f"Chromium install failed (exit {_pw_code})")
        with st.expander("Install log"):
            st.code(_pw_out or "(no stdout)")
            st.code(_pw_err or "(no stderr)")
    else:
        st.success("✅ Chromium installed")

    st.markdown("---")
    st.markdown("### 🩺 Diagnostics")
    if st.button("Test Chromium launch", use_container_width=True):
        with st.spinner("Testing …"):
            diag = subprocess.run([sys.executable, "-c", """
import asyncio
from playwright.async_api import async_playwright
async def test():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-dev-shm-usage","--disable-gpu",
                  "--single-process","--no-zygote"])
        page = await browser.new_page()
        await page.goto("https://example.com", timeout=15000)
        title = await page.title()
        await browser.close()
        return title
print(asyncio.run(test()))
"""], capture_output=True, text=True, timeout=60)
        if diag.returncode == 0:
            st.success(f"✅ Browser works! Title: {diag.stdout.strip()}")
        else:
            st.error("❌ Browser launch failed")
            st.code(diag.stdout); st.code(diag.stderr)

    # ── URL preview tool ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🔗 URL preview")
    t_last  = st.text_input("Lastname",  "CHAVENT", key="diag_last")
    t_first = st.text_input("Firstname", "Pascal",  key="diag_first")

    def _slugify(text):
        text = unidecode(str(text)).lower().strip()
        return re.sub(r"[^a-z0-9]+", "", text)

    preview_url = f"https://www.betrail.run/runner/{_slugify(t_last)}.{_slugify(t_first)}/overview"
    st.code(preview_url, language=None)

    if st.button("🔍 Scrape this runner (debug)", use_container_width=True):
        with st.spinner("Scraping …"):
            debug_script = f"""
import asyncio, re
from playwright.async_api import async_playwright

XPATH = (
    "/html/body/app-root/div/div/div/runner-page/div/div/"
    "app-runner-overview/div/div[1]/div/bt-card[1]/div/div[3]/"
    "div[1]/div/runner-level/div/runner-score/div"
)

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-dev-shm-usage","--disable-gpu",
            "--single-process","--no-zygote"
        ])
        page = await browser.new_page()
        print("GOTO:", "{preview_url}")
        resp = await page.goto("{preview_url}", wait_until="domcontentloaded", timeout=30000)
        print("STATUS:", resp.status if resp else "None")

        # Wait for Angular to hydrate
        await page.wait_for_timeout(5000)

        # Try XPath
        try:
            loc = page.locator("xpath=" + XPATH)
            await loc.wait_for(timeout=10000)
            text = (await loc.inner_text()).strip()
            print("SCORE_XPATH:", text)
        except Exception as e:
            print("XPATH_FAIL:", e)

        # Try CSS selector as fallback
        try:
            loc2 = page.locator("runner-score div")
            count = await loc2.count()
            print("CSS_RUNNER_SCORE_COUNT:", count)
            if count > 0:
                for i in range(count):
                    t = (await loc2.nth(i).inner_text()).strip()
                    print(f"  CSS[{{i}}]:", t)
        except Exception as e:
            print("CSS_FAIL:", e)

        # Dump page title and URL
        print("TITLE:", await page.title())
        print("URL:", page.url)

        # Dump all text nodes that look like numbers between 0-1000
        content = await page.content()
        nums = re.findall(r'\\b([0-9]{{1,4}})\\b', content)
        print("NUMERIC_TOKENS (sample):", list(set(nums))[:30])

        await browser.close()

asyncio.run(run())
"""
            dbg = subprocess.run(
                [sys.executable, "-c", debug_script],
                capture_output=True, text=True, timeout=90
            )
        st.markdown("**Debug output:**")
        st.code(dbg.stdout or "(no stdout)")
        if dbg.stderr:
            st.code(dbg.stderr)

# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = unidecode(str(text)).lower().strip()
    return re.sub(r"[^a-z0-9]+", "", text)

def build_url(lastname: str, firstname: str) -> str:
    return f"https://www.betrail.run/runner/{slugify(lastname)}.{slugify(firstname)}/overview"

XPATH = (
    "/html/body/app-root/div/div/div/runner-page/div/div/"
    "app-runner-overview/div/div[1]/div/bt-card[1]/div/div[3]/"
    "div[1]/div/runner-level/div/runner-score/div"
)

async def scrape_one(url: str, browser) -> str:
    page = await browser.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if resp and resp.status == 404:
            return "not found"
        # Give Angular time to render after DOM load
        await page.wait_for_timeout(5000)
        try:
            loc = page.locator(f"xpath={XPATH}")
            await loc.wait_for(timeout=10_000)
            text = (await loc.inner_text()).strip()
            m = re.search(r"[\d,.]+", text)
            return m.group(0) if m else text
        except Exception:
            # Fallback: try CSS selector
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
        await page.close()

async def scrape_all(rows: list, progress_cb, log_cb) -> list:
    from playwright.async_api import async_playwright
    MAX_CONCURRENT = 2
    scores = [""] * len(rows)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-dev-shm-usage","--disable-gpu",
                  "--single-process","--no-zygote"],
        )
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
    '<span class="badge">v1.4</span></div>', unsafe_allow_html=True)
st.markdown("<p style='color:#888;margin-top:0.25rem'>Upload a CSV of runners → "
            "fetch their Betrail scores → download enriched CSV.</p>", unsafe_allow_html=True)
st.divider()

# ── Upload ────────────────────────────────────────────────────────────────────
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

# ── Scrape ────────────────────────────────────────────────────────────────────
if df is not None:
    if st.button("🚀 Start scraping", type="primary", use_container_width=True):
        total = len(df)
        progress_bar = st.progress(0, text="Initialising …")
        status_text  = st.empty()
        log_area     = st.expander("📋 Live scraping log", expanded=True)
        log_lines    = []

        def update_progress(done: int):
            progress_bar.progress(done / total, text=f"Scraping runner {done} / {total} …")
            status_text.markdown(f"<small style='color:#888'>Completed: {done}/{total}</small>",
                                 unsafe_allow_html=True)

        def log_cb(idx, last, first, url, score):
            icon = "✅" if score not in ("not found","") and not score.startswith("error") else (
                   "⚠️" if score == "not found" else "❌")
            line = f"{icon} [{idx+1}] {last} {first} → `{score}` | {url}"
            log_lines.append(line)
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

        found     = sum(1 for s in scores if s not in ("not found","","") and not str(s).startswith("error"))
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
            use_container_width=True, height=420
        )

        st.divider()
        st.download_button("⬇️ Download enriched CSV",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="runners_with_scores.csv", mime="text/csv",
            type="primary", use_container_width=True)
