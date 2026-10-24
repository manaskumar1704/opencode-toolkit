name: free-tier-deploy
description: Operational checklist for deploying and running this stack (Render free web service, Vercel frontend, Neon Postgres, GitHub Actions) learned from the Oct 2026 deploy. Load before any deployment, redeploy, environment-variable change, or database credential rotation.
---

# Free-tier deploy checklist (Render free + Vercel + Neon)

Every item here was paid for with a real outage or a silently failed deploy.

## Render (the API)

1. **Free tier has no `preDeployCommand`.** Migrations run in the image's own
   CMD (`sh -c "alembic upgrade head && exec uvicorn ..."`). Docker `CMD` does
   not inherit a shell, so the command must be shell-wrapped, or `alembic`
   receives `&& uvicorn ...` as its own arguments and exits 2.
2. **A failed boot keeps the previous image serving.** The docs' design relies
   on it: if migrations die, the old container keeps answering while every new
   deploy fails. Symptom: code changes land on GitHub, CI is green, but prod
   behaviour never changes. Check the deploy log, not the check runs.
3. **`autoDeployTrigger: checksPass`** means a deploy starts only after green
   CI, and Vercel deploys the same push immediately. The two halves can be on
   different versions for minutes.
4. **Uptime monitors default to HEAD.** Starlette 1.7 (FastAPI 0.143) no longer
   derives HEAD from GET routes, so `/health` and `/ready` must declare
   `methods=["GET", "HEAD"]` explicitly, and a test pins it.
5. **Render rotates its internal proxy peer on every deploy** (observed three
   different `10.x` peers in one hour). `TRUSTED_PROXY_CIDRS` must name the
   Render internal range (`10.0.0.0/8`) plus Cloudflare's published edge ranges,
   never a pinned `/32`. Verify from the header probe, not from memory.
6. **GitHub disables scheduled workflows on public repos after 60 days of
   inactivity.** The keep-alive cron is not a guarantee; the external monitor is
   the permanent check. Also, GitHub throttles `*/8` crons to roughly a slot
   every few hours on the free plan.
7. **`buildFilter` skipping `apps/web/**` means a frontend-only commit never
   redeploys the API.** That is by design (each API build re-bakes the 67 MB
   embedding model).

## Neon (the database)

1. **Password resets are branch-scoped.** A reset on one branch changes only
   that branch's role password. Reset the *production* branch's `neondb_owner`
   in the console, not the branch your local `.env` points at.
2. **The app needs BOTH URLs**: pooled (`-pooler` host) for runtime
   (`DATABASE_URL`) and direct (no `-pooler`) for Alembic (`SYNC_DATABASE_URL`).
   Transaction-pooler connections misroute DDL and session state.
3. **Compute suspends after 5 idle minutes.** One `OperationalError` from a
   tool mid-chat is usually a waking compute, not a code failure. Confirm with
   `/ready` before debugging deeper.

## Verification order for every deploy

1. `curl /health` (liveness, no DB), then `curl /ready` (DB truth).
2. Run one real tool call through `POST /chat` (retrieval + a data tool).
3. Then open the browser. Reproduce locally with a throwaway script before
   blaming production data.

See `docs/retro-oct2026.md` for the incidents behind each rule.
