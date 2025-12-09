
# grok-trader

Grok Trader brings data to your fingertips, giving the average person the insights of a trading analyst for any prediction market (currently, we support [Polymarket](https://polymarket.com/)). The tool streams live sentiment data, pulling news and social signals (X, Reddit, Reuters), and delivers research/analysis through LLM-powered inferencing. Results are displayed in a Chrome sidebar. Built for the 2025 xAI Hackathon by [Ayush Gundawar](https://github.com/ayushgun), [Aryan Gupta](https://github.com/aryan-cs), and [Yuming He](https://github.com/yuming-h).

## What it does
- Streams market-aware sentiment and links in real time via WebSocket (FastAPI).
- Runs research and follow-up analysis with xAI models, returning structured reasoning and citations.
- Surfaces news/social signals from X, Reddit, and Reuters.
- Provides a Chrome/Vite React sidebar that auto-loads for the active Polymarket event page.
- Supports auto-trade scaffolding and backtesting utilities for experimentation.

## Tech stack
- Backend: FastAPI, asyncio, websockets, Polymarket feed, requests/httpx, xai-sdk, tweepy, praw.
- Frontend: React + Vite (Chrome extension sidebar), react-markdown.
- Data feeds: X/Twitter v2, Reddit public JSON, Google News (Reuters), Polymarket orderbooks.

## Prerequisites
- Python 3.12+
- Node.js 18+
- Chrome/Brave (to load the extension)

### Required environment
Create a `.env` in the repo root with the keys you have:

```
# xAI / LLM
XAI_API_KEY=your_xai_key

# Feeds
X_BEARER_TOKEN=your_twitter_bearer
REDDIT_USER_AGENT=python:grok-trader:v1.0 (by /u/you)

# Optional: OpenAI or other providers if you wire them in
OPENAI_API_KEY=your_openai_key
```

## Backend setup
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
uv run main.py
```

This starts the WebSocket/HTTP server the extension talks to.

## Frontend (Chrome extension) setup
```powershell
npm install
npm run build
```

Then load the built extension:
1) Open `chrome://extensions/` and enable Developer Mode.
2) Click “Load unpacked” and select `client/dist`.
3) Navigate to a Polymarket event page; the sidebar should appear and connect to `ws://localhost:8765/ws`.

For rapid UI work you can run the Vite dev server, but loading the unpacked build is the intended flow for the extension.

## Usage
- Select a market in the sidebar; it will immediately stream sentiment/items.
- Use Chat or Deep Research tabs for LLM-driven analysis and follow-ups.
- Auto Trader tab stores watch conditions (execution logic is scaffolded).

## Notes
- CSV outputs (tweets/reddit/reuters/grokipedia) are ignored by git; they’re in `datafeed/**`.
- The app assumes `localhost:8765`; adjust in `client/src/Sidebar.jsx` if you change ports.


