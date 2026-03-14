#!/bin/bash
# Streamlit Community Cloud runs this script before starting the app.
# It installs Playwright's Chromium binary + system dependencies.
pip install playwright --quiet
playwright install chromium --with-deps
