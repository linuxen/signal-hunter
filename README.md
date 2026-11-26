# FeedWatch Starter

A local RSS keyword monitor built with FastAPI, HTMX, Jinja2, SQLite, and APScheduler. Add a keyword, then click **Scan now** or wait for the scheduled scan. A keyword matches when it appears in an entry's title or description, ignoring case. SQLite stores keywords and matches across restarts.

## Run locally

With Python 3.12:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m uvicorn app.main:app
```

With Docker Compose:

```sh
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). The app creates the SQLite database and tables on startup. The defaults are `data/feedwatch.db` and a scan every 30 minutes. Copy `.env.example` to `.env` to override them. Docker Compose persists the default database path in a named volume. Run one Uvicorn worker so only one scheduler runs.

## Project layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI app, scheduler and health endpoint |
| `app/database.py`, `app/models.py` | SQLite setup and data models |
| `app/routers/web.py`, `app/templates/` | Keyword form and results, updated with HTMX |
| `app/services/` | Keyword registration, feed parsing, matching and scans |
| `tests/` | Offline tests with mocked feed responses |

The two demo feeds are Hacker News and Python Insider. Edit the `FEEDS` tuple in [`app/services/feeds.py`](app/services/feeds.py) to add or replace RSS or Atom feeds.

## Tests

```sh
python -m unittest discover -v
```

MIT licensed.
