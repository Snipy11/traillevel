import streamlit as st
import pandas as pd
import asyncio
import re
import json
import traceback
from unidecode import unidecode

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

# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unidecode(str(text)).lower().strip())

def build_api_url(lastname: str, firstname: str) -> str:
    return f"https://www.betrail.run/api/runner/{slugify(lastname)}.{slugify(firstname)}"

def build_referer(lastname: str, firstname: str) -> str:
    return f"https://www.betrail.run/runner/{slugify(lastname)}.{slugify(firstname)}/overview"

def make_headers(cookie: str, lastname: str = "chavent", firstname: str = "pascal") -> dict:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "fr,fr-FR;q=0.9,en;q=0.8",
        "referer": build_referer(lastname, firstname),
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
        ),
        "cookie": cookie,
    }

# ── Score extraction — will be updated once we see the real JSON ──────────────
# SCORE_KEY will be set to the correct key once the user tests and shares JSON
SCORE_KEY = st.session_state.get("score_key", "")

def extract_score(data, score_key: str = "") -> str:
    """Walk the JSON to find the score value."""
    if not data:
        return "not found"

    # If user has configured the exact key path (e.g. "level.score" or "score")
    if score_key:
        parts = score_key.split(".")
        val = data
        try:
            for p in parts:
                val = val[p] if isinstance(val, dict) else val[int(p)]
            if val not in (None, "", 0):
                return str(val)
        except Exception:
            pass

    # Auto-detect: common score key names used by running/trail apps
    CANDIDATE_KEYS = [
        "score", "betrailScore", "betrail_score",
        "level", "itra", "itraScore", "itra_score",
        "runnerScore", "runner_score", "index",
        "performance", "ranking",
    ]
    if isinstance(data, dict):
        # Top-level
        for k in CANDIDATE_KEYS:
            if k in data and data[k] not in (None, "", 0):
                return str(data[k])
        # One level deep
        for v in data.values():
            if isinstance(v, dict):
                for k in CANDIDATE_KEYS:
                    if k in v and v[k] not in (None, "", 0):
                        return str(v[k])
    return "not found"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")

    cookie_val = st.text_area(
        "🍪 Cookie (from your browser)",
        value=st.session_state.get("cookie_val", ""),
        placeholder="Paste the full Cookie: header value here",
        height=100,
        key="cookie_input",
        help="F12 → Network → /api/runner/... → Request Headers → Cookie"
    )
    st.session_state["cookie_val"] = cookie_val

    score_key_input = st.text_input(
        "🎯 Score JSON key path (fill after test below)",
        value=st.session_state.get("score_key", ""),
        placeholder="e.g.  score  or  runner.level  or  data.0.score",
        help="Dot-separated path to the score in the JSON. Leave blank for auto-detect.",
        key="score_key_input",
    )
    st.session_state["score_key"] = score_key_input

    st.markdown("---")
    st.markdown("### 🔍 Test one runner")

    t_last  = st.text_input("Lastname",  "CHAVENT", key="diag_last")
    t_first = st.text_input("Firstname", "Pascal",  key="diag_first")
    api_url_preview = build_api_url(t_last, t_first)
    st.code(api_url_preview, language=None)

    if st.button("🧪 Test API call + show JSON", use_container_width=True):
        if not cookie_val.strip():
            st.warning("Paste your Cookie header first.")
        else:
            import httpx
            with st.spinner("Calling API …"):
                try:
                    hdrs = make_headers(cookie_val.strip(), t_last, t_first)
                    r = httpx.get(api_url_preview, headers=hdrs,
                                  timeout=15, follow_redirects=True)
                    st.write(f"**Status:** `{r.status_code}`")
                    if r.status_code == 200:
                        data = r.json()
                        score = extract_score(data, score_key_input)
                        if score != "not found":
                            st.success(f"✅ Score found: **{score}**")
                        else:
                            st.warning("⚠️ Score not auto-detected. "
                                       "Look at the JSON below and fill in the "
                                       "**Score JSON key path** field above.")
                        st.markdown("**Full JSON response:**")
                        st.json(data)
                    elif r.status_code == 403:
                        st.error(
                            "403 — Cloudflare blocked the request. "
                            "The `cf_clearance` cookie is tied to your browser IP. "
                            "See explanation below. ⬇️"
                        )
                        st.code(r.text[:300])
                    else:
                        st.error(f"HTTP {r.status_code}")
                        st.code(r.text[:300])
                except Exception as e:
                    st.error(str(e))

# ── Scraper ───────────────────────────────────────────────────────────────────

async def fetch_score_async(client, lastname: str, firstname: str,
                             cookie: str, score_key: str) -> str:
    url = build_api_url(lastname, firstname)
    try:
        hdrs = make_headers(cookie, lastname, firstname)
        r = await client.get(url, headers=hdrs, timeout=15)
        if r.status_code == 404:
            return "not found"
        if r.status_code == 403:
            return "error: 403 Cloudflare"
        if r.status_code != 200:
            return f"error: HTTP {r.status_code}"
        data = r.json()
        return extract_score(data, score_key)
    except Exception as e:
        return f"error: {type(e).__name__}: {str(e)[:60]}"


async def scrape_all(rows, cookie, score_key, progress_cb, log_cb):
    import httpx
    scores = [""] * len(rows)
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=5)

    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        semaphore = asyncio.Semaphore(5)

        async def task(idx, row):
            async with semaphore:
                score = await fetch_score_async(
                    client, row["lastname"], row["firstname"], cookie, score_key)
            scores[idx] = score
            log_cb(idx, row.get("lastname","?"), row.get("firstname","?"), score)
            progress_cb(idx + 1)

        await asyncio.gather(*[task(i, r) for i, r in enumerate(rows)])
    return scores


def run_scraper(rows, cookie, score_key, progress_cb, log_cb):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run,
                             scrape_all(rows, cookie, score_key, progress_cb, log_cb))
        try:
            return future.result(timeout=600)
        except Exception as e:
            raise RuntimeError(f"{e}\n\n{traceback.format_exc()}") from e

# ── Main UI ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="title-bar"><h1 style="margin:0">🏃 Betrail Score Scraper</h1>'
    '<span class="badge">v2.1</span></div>', unsafe_allow_html=True)
st.markdown(
    "<p style='color:#888;margin-top:0.25rem'>"
    "Fetch Betrail scores for a list of runners via the Betrail API."
    "</p>", unsafe_allow_html=True)

# ── Cloudflare explanation ─────────────────────────────────────────────────────
with st.expander("ℹ️ How to get your Cookie — and why it may still return 403", expanded=False):
    st.markdown("""
**Why a cookie is needed**

Betrail's API is protected by Cloudflare. Every request must carry a `cf_clearance`
cookie that Cloudflare issues after a real browser solves a challenge.

**How to get it**
1. Open [betrail.run](https://www.betrail.run) in Chrome/Firefox (log in if you have an account)
2. Press **F12 → Network tab**
3. Navigate to any runner page, e.g. `/runner/chavent.pascal/overview`
4. In the Network tab, click the request to `/api/runner/chavent.pascal`
5. Under **Request Headers**, copy the entire `Cookie:` value
6. Paste it in the sidebar field **"🍪 Cookie"**

**Important limitation — Cloudflare IP binding**

The `cf_clearance` cookie is cryptographically bound to your browser's IP address.
When this Streamlit app (running on a Cloudflare/AWS datacenter IP) sends the same
cookie, Cloudflare detects the IP mismatch and returns **403**.

**Solutions (pick one)**
| Option | How |
|---|---|
| **Run locally** | `streamlit run app.py` on your own machine — same IP as your browser ✅ |
| **Use a VPN** | Connect your browser and the server to the same VPN exit node |
| **Betrail account API** | If Betrail offers an authenticated API, use a Bearer token instead |
    """)

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
    cookie = st.session_state.get("cookie_val", "").strip()
    score_key = st.session_state.get("score_key", "").strip()

    if not cookie:
        st.warning("⚠️ Paste your Cookie header in the sidebar before scraping.")

    col_btn, col_info = st.columns([2, 3])
    with col_btn:
        start = st.button("🚀 Start scraping", type="primary",
                          use_container_width=True, disabled=not cookie)
    with col_info:
        st.caption("Runs at up to 5 concurrent requests. ~1–3s per runner.")

    if start:
        total = len(df)
        progress_bar = st.progress(0, text="Initialising …")
        status_text  = st.empty()
        log_area     = st.expander("📋 Live log", expanded=True)
        log_lines    = []

        def update_progress(done):
            progress_bar.progress(done / total, text=f"Fetching {done}/{total} …")

        def log_cb(idx, last, first, score):
            is_ok = score not in ("not found","") and not str(score).startswith("error")
            icon = "✅" if is_ok else ("⚠️" if score == "not found" else "❌")
            log_lines.append(f"{icon} **{last} {first}** → `{score}`")
            log_area.markdown("\n\n".join(log_lines))

        rows = df.to_dict(orient="records")
        try:
            scores = run_scraper(rows, cookie, score_key, update_progress, log_cb)
        except Exception as exc:
            st.error(f"**Scraping failed.**\n\n```\n{exc}\n```")
            st.stop()

        progress_bar.progress(1.0, text="Done ✓")

        result_df = df.copy()
        result_df["betrail_score"] = scores

        found     = sum(1 for s in scores if s not in ("not found","") and not str(s).startswith("error"))
        not_found = sum(1 for s in scores if s == "not found")
        errors    = sum(1 for s in scores if str(s).startswith("error"))

        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        for col, num, lbl in [(c1,total,"Total"),(c2,found,"Found"),
                               (c3,not_found,"Not found"),(c4,errors,"Errors")]:
            with col:
                st.markdown(f'<div class="metric-box"><div class="metric-num">{num}</div>'
                            f'<div class="metric-lbl">{lbl}</div></div>',
                            unsafe_allow_html=True)

        st.divider()
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
