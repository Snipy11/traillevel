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
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr

_pw_code, _pw_out, _pw_err = _install_playwright()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Betrail Score Scraper",
    page_icon="🏃",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Space Mono', monospace; }
.stApp { background: #0d0d0d; color: #e8e8e8; }
.block-container { padding-top: 2rem; max-width: 1100px; }
.title-bar { display: flex; align-items: center; gap: 14px; margin-bottom: 0.25rem; }
.badge {
    background: #00e5a0; color: #000;
    font-family: 'Space Mono', monospace; font-size: 0.65rem; font-weight: 700;
    padding: 3px 8px; border-radius: 3px; letter-spacing: 0.08em;
    text-transform: uppercase; vertical-align: middle;
}
.metric-box {
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 1rem 1.5rem; text-align: center;
}
.metric-num { font-family: 'Space Mono', monospace; font-size: 2rem; font-weight: 700; color: #00e5a0; }
.metric-lbl { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 0.08em; }
</style>
""", unsafe_allow_html=True)

# ── Chromium install status ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔧 System status")
    if _pw_code != 0:
        st.error(f"Chromium install failed (exit {_pw_code})")
        with st.expander("Install log"):
            st.code(_pw_out or "(no stdout)")
            st.code(_pw_err or "(no stderr)")
    else:
        st.success("✅ Chromium installed")

    # ── Diagnostic button ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🩺 Diagnostics")
    if st.button("Test Chromium launch", use_container_width=True):
        with st.spinner("Launching a test browser page …"):
            diag_result = subprocess.run(
                [sys.executable, "-c", """
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]
        )
        page = await browser.new_page()
        await page.goto("https://example.com", timeout=15000)
        title = await page.title()
        await browser.close()
        return title

print(asyncio.run(test()))
"""],
                capture_output=True,
                text=True,
                timeout=60,
            )
        if diag_result.returncode == 0:
            st.success(f"✅ Browser works! Page title: {diag_result.stdout.strip()}")
        else:
            st.error("❌ Browser launch failed")
            st.code(diag_result.stdout)
            st.code(diag_result.stderr)

# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = unidecode(str(text)).lower().strip()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def build_url(lastname: str, firstname: str) -> str:
    slug = f"{slugify(lastname)}.{slugify(firstname)}"
    return f"https://www.betrail.run/runner/{slug}/overview"


XPATH = (
    "/html/body/app-root/div/div/div/runner-page/div/div/"
    "app-runner-overview/div/div[1]/div/bt-card[1]/div/div[3]/"
    "div[1]/div/runner-level/div/runner-score/div"
)


async def scrape_one(url: str, browser) -> str:
    page = await browser.new_page()
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=30_000)
        if response and response.status == 404:
            return "not found"
        try:
            locator = page.locator(f"xpath={XPATH}")
            await locator.wait_for(timeout=15_000)
            text = (await locator.inner_text()).strip()
            match = re.search(r"[\d,.]+", text)
            return match.group(0) if match else text
        except Exception:
            return "not found"
    except Exception as e:
        return f"error: {type(e).__name__}"
    finally:
        await page.close()


async def scrape_all(rows: list, progress_cb) -> list:
    from playwright.async_api import async_playwright

    MAX_CONCURRENT = 3  # reduced to avoid memory pressure on free tier
    scores = [""] * len(rows)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",          # critical for constrained containers
                "--no-zygote",
            ],
        )
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def task(idx: int, row: dict):
            url = build_url(row["lastname"], row["firstname"])
            async with semaphore:
                score = await scrape_one(url, browser)
            scores[idx] = score
            progress_cb(idx + 1)

        await asyncio.gather(*[task(i, r) for i, r in enumerate(rows)])
        await browser.close()

    return scores


def run_scraper(rows: list, progress_cb) -> list:
    """
    Run async scraper from Streamlit's sync context.
    Tornado owns the main-thread event loop, so we use a worker thread.
    """
    import concurrent.futures
    exc_holder = []

    def _run():
        try:
            return asyncio.run(scrape_all(rows, progress_cb))
        except Exception as e:
            exc_holder.append(e)
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        try:
            return future.result(timeout=600)
        except Exception as e:
            # Re-raise with full traceback visible in the UI
            full_tb = traceback.format_exc()
            raise RuntimeError(f"{e}\n\nFull traceback:\n{full_tb}") from e


# ── Streamlit UI ──────────────────────────────────────────────────────────────

st.markdown(
    '<div class="title-bar">'
    '<h1 style="margin:0">🏃 Betrail Score Scraper</h1>'
    '<span class="badge">v1.3</span>'
    "</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='color:#888;margin-top:0.25rem'>"
    "Upload a CSV of runners → fetch their Betrail scores → download enriched CSV."
    "</p>",
    unsafe_allow_html=True,
)
st.divider()

# ── Upload ────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload your CSV file",
    type=["csv"],
    help="Expected columns: lastname, firstname, name, team, bibNumber, competition.reportName",
)

df = None

if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=None, engine="python", dtype=str)
        df.columns = [c.strip() for c in df.columns]
        col_lower = {c.lower(): c for c in df.columns}
        missing = [r for r in ["lastname", "firstname"] if r not in col_lower]
        if missing:
            st.error(f"CSV is missing required columns: {', '.join(missing)}")
            df = None
        else:
            # Normalise column name casing for internal use
            df = df.rename(columns={
                col_lower.get("lastname", "lastname"): "lastname",
                col_lower.get("firstname", "firstname"): "firstname",
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
        status_text = st.empty()
        error_box = st.empty()

        def update_progress(done: int):
            pct = done / total
            progress_bar.progress(pct, text=f"Scraping runner {done} / {total} …")
            status_text.markdown(
                f"<small style='color:#888'>Completed: {done}/{total}</small>",
                unsafe_allow_html=True,
            )

        rows = df.to_dict(orient="records")

        with st.spinner("Launching browser …"):
            try:
                scores = run_scraper(rows, update_progress)
            except Exception as exc:
                error_box.error(
                    f"**Scraping failed.**\n\n```\n{exc}\n```"
                )
                st.stop()

        progress_bar.progress(1.0, text="Done ✓")
        status_text.empty()

        result_df = df.copy()
        result_df["betrail_score"] = scores

        found     = sum(1 for s in scores if s not in ("not found", "error", "") and not str(s).startswith("error:"))
        not_found = sum(1 for s in scores if s == "not found")
        errors    = sum(1 for s in scores if str(s).startswith("error"))

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        for col, num, lbl in [
            (c1, total, "Total runners"),
            (c2, found, "Scores found"),
            (c3, not_found, "Not found"),
            (c4, errors, "Errors"),
        ]:
            with col:
                st.markdown(
                    f'<div class="metric-box">'
                    f'<div class="metric-num">{num}</div>'
                    f'<div class="metric-lbl">{lbl}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.divider()
        st.subheader("Results")

        display_cols = []
        for candidate in ["name", "bibNumber", "competition.reportName", "betrail_score"]:
            matched = next(
                (c for c in result_df.columns if c.lower() == candidate.lower()), None
            )
            if matched:
                display_cols.append(matched)
            elif candidate == "betrail_score":
                display_cols.append("betrail_score")

        if not display_cols:
            display_cols = list(result_df.columns)

        display_df = result_df[display_cols].copy()

        def style_score(val):
            v = str(val)
            if v == "not found":
                return "color: #ff6b6b; font-style: italic"
            if v.startswith("error"):
                return "color: #ffa94d; font-style: italic"
            return "color: #00e5a0; font-weight: 700; font-family: monospace"

        styled = display_df.style.map(style_score, subset=["betrail_score"])
        st.dataframe(styled, use_container_width=True, height=420)

        st.divider()
        csv_bytes = result_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download enriched CSV",
            data=csv_bytes,
            file_name="runners_with_scores.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )
