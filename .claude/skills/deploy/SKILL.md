---
name: deploy
description: Deploy the Congress Trades Tracker backend (Vercel) and/or frontend (Netlify) to production. Use whenever the user asks to deploy, publish, push live, or ship changes for this project — neither service auto-deploys from GitHub, so every change needs a manual redeploy through this skill.
---

# Deploy Congress Trades Tracker

Neither Netlify nor Vercel is connected to the GitHub repo for auto-deploy —
both were created via their CLIs. Every change needs a manual redeploy.

## Prerequisites

Both CLIs must already be authenticated on this machine (`netlify status`,
`npx vercel whoami`). If not, see CLAUDE.md's "En vivo" section for the
account emails, or ask the user — do not create new accounts without asking.

## Backend (only if you touched `backend/`)

```bash
cd /d/proyectos/congress-trades-tracker
npx --yes vercel deploy --prod --yes
```

After deploying, sanity-check with a couple of real endpoints before telling
the user it's done:

```bash
curl -s https://congress-trades-tracker-api.vercel.app/health
curl -s https://congress-trades-tracker-api.vercel.app/kpis
```

**If you added a new top-level import** (anything not already inside
`backend/app/`), read CLAUDE.md's "Vercel solo empaqueta..." section first —
it will silently `ModuleNotFoundError` in production while working fine
locally. Move the module into `app/` before deploying.

## Frontend (almost always, after any frontend/ or backend API-shape change)

```bash
cd /d/proyectos/congress-trades-tracker/frontend
VITE_API_BASE="https://congress-trades-tracker-api.vercel.app" npm run build
cd ..
netlify deploy --prod
```

`VITE_API_BASE` must be set on that exact build command — a plain `npm run
build` bakes in the local dev proxy path instead and the deployed site will
fail to load any data.

## Verify visually before reporting done

Take a real screenshot against the live URL, not just curl — this project has
shipped rendering-only bugs (misplaced chart markers, encoding mojibake) that
curl/JSON checks alone wouldn't catch. Use Playwright:

```bash
cd frontend
npm install -D playwright --no-save
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto('https://congress-trades-tracker.netlify.app/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: '<scratchpad>/deploy_check.png' });
  await browser.close();
})();
"
```

**Then immediately `npm uninstall playwright`** (or use `--no-save` and check
`git diff frontend/package.json` before any commit) — it has accidentally
been committed as a dependency multiple times this project's history. Never
leave it in `package.json`.

## Committing the SQLite DB

If your change touched `backend/data/congress_trades.db` (e.g. you ran
`calculate_rankings.py` or `fetch_trades.py` locally), `git pull` before
committing — the three GitHub Actions crons (`ingest.yml`, `bot-poll.yml`,
`rankings.yml`) write to this file constantly and a stale local copy will
conflict. A conflict on this binary can't be merged — resolve with
`git checkout --ours backend/data/congress_trades.db` (keep remote/HEAD) or
`--theirs` (keep your local copy), whichever actually has the change you
care about, then `git add` it.
