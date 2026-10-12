# Deploying AlphaBacktest

One container serves the API and the built frontend from the same address, backed by Postgres. The steps below use [Render](https://render.com), configured by `render.yaml` in the repo root. Any host that runs a Docker image works the same way with the settings in the table.

## What gets deployed

- `Dockerfile` builds the frontend (`npm run build`), then runs the FastAPI server, which serves `frontend/dist` and `/api/*` together. No CORS and no second site.
- Postgres stores users and saved strategies. Do not use SQLite on a host: its disk is wiped on every deploy.

## Settings

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | the Postgres connection string | `postgres://` and `postgresql://` URLs are accepted as-is |
| `GOOGLE_CLIENT_ID` | your OAuth client ID | Not a secret (it is public in the page), but it is not in the repo. Set it in the host's dashboard |
| `SESSION_SECRET` | long random string | A secret. Render generates it for you. Changing it signs everyone out |
| `COOKIE_SECURE` | `1` | The site is on HTTPS, so the cookie must be HTTPS-only |
| `PORT` | set by the host | The container listens on it (default 8080) |

If `GOOGLE_CLIENT_ID` is missing, **login is off and every visitor shares one user**. Always set it on a public site.

## Steps on Render

1. Push the repo to GitHub (it already is).
2. In Render: **New → Blueprint**, pick the repo. Render reads `render.yaml` and proposes a web service plus a Postgres database.
3. When asked for `GOOGLE_CLIENT_ID`, paste the client ID exactly as Google shows it (it already ends in `.apps.googleusercontent.com`).
4. Apply. The first build takes a few minutes. You get an address like `https://alphabacktest.onrender.com`.
5. **Tell Google about the new address.** In Google Cloud Console → Credentials → your OAuth client → **Authorized JavaScript origins**, add `https://alphabacktest.onrender.com` (your real address, `https`, no trailing slash). Keep `http://localhost:5173` for local development. Changes can take a few minutes.
6. Open the site, click **Sign in**, save a strategy, and run a backtest.

Later, every push to `main` redeploys automatically.

### Custom domain

Add it in Render (Settings → Custom Domains), then add `https://your-domain` to Authorized JavaScript origins as well.

## Things to know

- **Free-tier limits (Render):** the web service sleeps after ~15 minutes without traffic, so the first request takes about a minute. The free Postgres database expires after 30 days. For anything lasting, use a paid database, or a free external one such as [Neon](https://neon.tech) by setting `DATABASE_URL` yourself instead of using the blueprint's database.
- **Yahoo Finance may block cloud servers.** It works from home networks, but Yahoo sometimes rate-limits the shared IP ranges that hosts use. If every backtest returns "Historical market data could not be loaded", this is the likely cause. The fix is a different data source in `backend/alphabacktest/data.py`.
- **Anyone can run backtests without signing in**, and each one calls Yahoo. There is no rate limiting yet.
- **No migrations:** tables are created on startup. Adding columns to existing tables later needs a migration tool such as Alembic.

## Trying the image locally

```bash
docker build -t alphabacktest .
docker run -p 8080:8080 alphabacktest
```

Open http://localhost:8080. This uses SQLite inside the container and login is off unless you also pass `-e GOOGLE_CLIENT_ID=... -e SESSION_SECRET=...`.
