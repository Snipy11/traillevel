import streamlit as st
import pandas as pd
import asyncio
import subprocess
import sys
import re
from unidecode import unidecode

# ── Ensure Playwright browser binary is installed ─────────────────────────────
# On Streamlit Community Cloud the Python package is present but the browser
# executable is NOT pre-installed.  We run `playwright install chromium` once
# per container start-up (cached in st.session_state so it only runs once per
# session, but the subprocess itself is idempotent so re-running is harmless).
@st.cache_resource(show_spinner="Installing Chromium browser (first run only) …")
def _install_playwright():
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Surface the error so we can debug it
        raise RuntimeError(
            f"playwright install failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return True

_install_playwright()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Betrail Score Scraper",
    page_icon="🏃",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }
    h1, h2, h3 {
        font-family: 'Space Mono', monospace;
    }
    .stApp {
        background: #0d0d0d;
        color: #e8e8e8;
    }
    .block-container {
        padding-top: 2rem;
        max-width: 1100px;
    }
    .title-bar {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 0.25rem;
    }
    .badge {
        background: #00e5a0;
        color: #000;
        font-family: 'Space Mono', monospace;
        font-size: 0.65rem;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 3px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        vertical-align: middle;
    }
    .score-found   { color: #00e5a0; font-weight: 700; font-family: 'Space Mono', monospace; }
    .score-missing { color: #ff6b6b; font-style: italic; }
    .score-error   { color: #ffa94d; font-style: italic; }
    .metric-box {
        background: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 8px;
        padding: 1rem 1.5rem;
        text-align: center;
    }
    .metric-num {
        font-family: 'Space Mono', monospace;
        font-size: 2rem;
        font-weight: 700;
        color: #00e5a0;
    }
    .metric-lbl {
        font-size: 0.8rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a name fragment to betrail slug (lowercase, no accents, no spaces)."""
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
    """Return the betrail score string for a single URL."""
    page = await browser.new_page()
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=30_000)
        if response and response.status == 404:
            return "not found"

        # Try to locate the score element
        try:
            locator = page.locator(f"xpath={XPATH}")
            await locator.wait_for(timeout=15_000)
            text = (await locator.inner_text()).strip()
            # Extract numeric part
            match = re.search(r"[\d,.]+", text)
            return match.group(0) if match else text
        except Exception:
            # Element not present → runner page exists but score unavailable
            return "not found"
    except Exception:
        return "error"
    finally:
        await page.close()


async def scrape_all(rows: list[dict], progress_cb) -> list[str]:
    """Scrape all runners with concurrency ≤ 5."""
    from playwright.async_api import async_playwright

    MAX_CONCURRENT = 5
    scores = [""] * len(rows)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
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


def run_scraper(rows: list[dict], progress_cb) -> list[str]:
    """
    Run the async scraper from a synchronous Streamlit context.

    Streamlit ≥ 1.18 executes in a thread that already has a running event
    loop (via tornado).  asyncio.run() raises 'cannot run nested event loop'
    in that situation.  We work around this by running the coroutine in a
    brand-new thread that has its own fresh event loop.
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, scrape_all(rows, progress_cb))
        return future.result()


# ── Streamlit UI ──────────────────────────────────────────────────────────────

st.markdown(
    '<div class="title-bar">'
    '<h1 style="margin:0">🏃 Betrail Score Scraper</h1>'
    '<span class="badge">v1.0</span>'
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

df: pd.DataFrame | None = None

if uploaded:
    try:
        df = pd.read_csv(uploaded, sep=None, engine="python", dtype=str)
        df.columns = [c.strip() for c in df.columns]

        # Normalize required column names (case-insensitive)
        col_map = {c.lower(): c for c in df.columns}
        required = ["lastname", "firstname"]
        missing = [r for r in required if r not in col_map]
        if missing:
            st.error(f"CSV is missing required columns: {', '.join(missing)}")
            df = None
        else:
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

        scraped = [0]

        def update_progress(done: int):
            scraped[0] = done
            pct = done / total
            progress_bar.progress(pct, text=f"Scraping runner {done} / {total} …")
            status_text.markdown(
                f"<small style='color:#888'>Completed: {done}/{total}</small>",
                unsafe_allow_html=True,
            )

        rows = df.to_dict(orient="records")

        with st.spinner("Launching browser …"):
            scores = run_scraper(rows, update_progress)

        progress_bar.progress(1.0, text="Done ✓")
        status_text.empty()

        # Attach scores to dataframe
        result_df = df.copy()
        result_df["betrail_score"] = scores

        # ── Summary metrics ────────────────────────────────────────────────
        found = sum(1 for s in scores if s not in ("not found", "error", ""))
        not_found = sum(1 for s in scores if s == "not found")
        errors = sum(1 for s in scores if s == "error")

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

        # Determine display columns
        display_cols = []
        for candidate in ["name", "bibNumber", "competition.reportName", "betrail_score"]:
            # case-insensitive lookup
            matched = next(
                (c for c in result_df.columns if c.lower() == candidate.lower()),
                None,
            )
            if matched:
                display_cols.append(matched)
            elif candidate == "betrail_score":
                display_cols.append("betrail_score")

        # Fallback: show all columns + betrail_score
        if not display_cols:
            display_cols = list(result_df.columns)

        display_df = result_df[display_cols].copy()

        # Style the score column
        def style_score(val):
            if val in ("not found",):
                return "color: #ff6b6b; font-style: italic"
            if val in ("error",):
                return "color: #ffa94d; font-style: italic"
            return "color: #00e5a0; font-weight: 700; font-family: monospace"

        styled = display_df.style.applymap(style_score, subset=["betrail_score"])
        st.dataframe(styled, use_container_width=True, height=420)

        # ── Download ───────────────────────────────────────────────────────
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
