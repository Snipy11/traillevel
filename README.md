# 🏃 Betrail Score Scraper

A Streamlit application that reads a CSV file of trail runners and automatically
retrieves their **Betrail score** from [betrail.run](https://www.betrail.run).

---

## Features

- Upload a CSV with runner details
- Automatically builds each runner's Betrail profile URL
- Scrapes the score using Playwright (headless Chromium)
- Concurrent scraping (up to 5 runners in parallel)
- Live progress bar during scraping
- Results table with colour-coded scores
- Download the enriched CSV with a `betrail_score` column

---

## Expected CSV format

```
lastname,firstname,name,team,bibNumber,competition.reportName
ABBOTT,Peter,Peter ABBOTT,,2282,10 km
CHAVENT,Pascal,Pascal CHAVENT,,123,31 km
```

Only **`lastname`** and **`firstname`** are strictly required for scraping.
The other columns are preserved in the export.

---

## Local installation & usage

### 1. Clone / download the project

```bash
git clone https://github.com/your-username/betrail-scraper.git
cd betrail-scraper
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright's Chromium browser

```bash
playwright install chromium --with-deps
```

> On Linux you may need to run `playwright install-deps chromium` as root if
> system libraries are missing.

### 5. Run the app

```bash
streamlit run app.py
```

Open <http://localhost:8501> in your browser.

---

## Deploying for free on Streamlit Community Cloud

### Prerequisites

- A free account on [share.streamlit.io](https://share.streamlit.io)
- The project pushed to a **public** (or private with access) GitHub repository

### Steps

1. **Push to GitHub**

   ```bash
   git init
   git add .
   git commit -m "initial commit"
   git remote add origin https://github.com/your-username/betrail-scraper.git
   git push -u origin main
   ```

2. **Connect to Streamlit Community Cloud**

   - Go to <https://share.streamlit.io> → *New app*
   - Select your repository, branch (`main`), and main file (`app.py`)
   - Click **Deploy**

3. **Playwright browser installation**

   Streamlit Community Cloud executes `setup.sh` automatically before launching
   the app (configured via the *Advanced settings → Pre-install script* field, or
   detected automatically when the file is present at the repo root).

   The `setup.sh` in this repo handles this:
   ```bash
   pip install playwright --quiet
   playwright install chromium --with-deps
   ```

   If your deployment does not pick up `setup.sh` automatically, go to
   **App settings → Advanced** and enter `bash setup.sh` in the
   *Pre-install command* field.

4. **That's it!** Your app will be live at
   `https://<your-username>-betrail-scraper-app-<hash>.streamlit.app`

---

## Project structure

```
.
├── app.py            # Main Streamlit application
├── requirements.txt  # Python dependencies
├── setup.sh          # Pre-install script for Playwright browsers
├── packages.txt      # (optional) additional apt packages for Streamlit Cloud
└── README.md         # This file
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `playwright._impl._errors.Error: Executable doesn't exist` | Run `playwright install chromium` |
| Score shows `not found` | The runner may not have a Betrail profile, or the name slug is wrong |
| Score shows `error` | Network timeout or the page structure changed; try re-running |
| Slow scraping | Normal — each page waits for JavaScript rendering (`networkidle`) |

---

## Notes on the Betrail URL slug

The URL slug is built as `lastname.firstname` after:
- converting accented characters to ASCII (`unidecode`)
- lowercasing everything
- removing all non-alphanumeric characters

Example: `CHÂTEAU, Éric` → `chateau.eric`

---

## License

MIT
