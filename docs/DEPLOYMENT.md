# Deploying Room for Both

Room for Both runs as two services from this one repository:

| Part | Host | Folder |
| --- | --- | --- |
| FastAPI backend | Render Web Service | `services/api` |
| Next.js frontend | Vercel | `apps/web` |
| NVIDIA Nemotron inference | Nebius Token Factory | called by the Render backend |

Nothing here has been deployed yet. These are the steps to do it. Never put a real key in a file,
a commit, a GitHub issue, a Vercel variable or anything under `NEXT_PUBLIC_*`.

Do the services in this order: backend first, then frontend, then point the backend's CORS
setting at the frontend.

## 1. Backend on Render

1. In Render, choose **New → Blueprint** and connect the public GitHub repository. Render reads
   [`render.yaml`](../render.yaml) at the repository root and proposes one web service,
   `room-for-both-api`.
2. When Render asks for the values marked as manual, enter them privately in the dashboard:
   - `NEBIUS_API_KEY` — your Nebius Token Factory key. Enter it only here.
   - `CORS_ALLOWED_ORIGINS` — the final Vercel production origin, for example
     `https://your-project.vercel.app` (no path, no trailing slash needed). You do not know it yet,
     so enter a placeholder and fix it in step 3 of the Vercel section. Use commas for several
     origins. **This value replaces the built-in `http://localhost:3000` default**, so local
     development is not allowed in production unless you list it.
3. Choose the instance plan in the dashboard. The Blueprint deliberately does not set one.
   - A free service sleeps when idle, so the first request after a pause can take about a minute
     (a cold start). The first analysis would then look broken.
   - For judging or a demo, an always-on plan with 512 MB of memory is recommended if affordable.
     The scheduler uses Google OR-Tools, so avoid anything smaller.
4. Deploy. The Blueprint uses Python 3.14.8 (`PYTHON_VERSION` and `services/api/.python-version`),
   installs `requirements.txt`, and starts `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   If Render does not offer that Python version, pick a supported 3.x version in the dashboard and
   confirm the `ortools` package installs on it.
5. Open the service URL, for example `https://room-for-both-api.onrender.com` (Render may assign a
   different name), and check:
   - `/health` returns `{"status":"healthy","service":"room-for-both-api"}`
   - `/openapi.json` loads
   - `POST /api/v1/evaluation/run` works without a key and reports 0 model calls

The backend starts and serves every route without `NEBIUS_API_KEY`. Only the model-dependent
analysis and repair ranking need it, and they fall back to their rule-based answers when it is
missing or the model is unreachable.

## 2. Frontend on Vercel

1. In Vercel, choose **Add New → Project** and import the same GitHub repository.
2. Set **Root Directory** to `apps/web`.
3. Confirm the framework is detected as **Next.js**. Keep the default build and output settings.
4. Add one environment variable, for **Production**:
   - Name: `NEXT_PUBLIC_API_BASE_URL`
   - Value: the Render service's HTTPS URL, for example `https://room-for-both-api.onrender.com`
   - Trailing slashes are removed automatically. Use `https`, or the browser blocks the calls as
     mixed content.
   - The value is read at build time, so changing it later needs a redeploy.
5. Deploy and note the final production origin (for example `https://your-project.vercel.app`).
6. Go back to Render, set `CORS_ALLOWED_ORIGINS` to that exact origin, and save. Render restarts
   the service; if it does not, restart or redeploy it manually.

Only the Vercel production origin you list is allowed. Preview deployments get a different origin
and are **not** allowed unless you add them to `CORS_ALLOWED_ORIGINS` yourself. A wildcard is never
accepted, and the API sends no cookies or credentials.

## 3. Notification worker headers

`/notification-sw.js` is served with `Cache-Control: no-cache, no-store, must-revalidate` and
`Service-Worker-Allowed: /` (configured in `apps/web/next.config.ts`), so an updated worker always
reaches users. No other route gets these headers. Browsers only register service workers on HTTPS
(or localhost), which Vercel provides.

## 4. Verify the live site

Open the Vercel URL and check each item. Watch the browser console throughout: there should be no
CORS or mixed-content errors.

- [ ] Home page loads
- [ ] `/setup` loads and "Review setup" succeeds
- [ ] `/evaluation` loads, and "Run verified evaluation" reports all cases passed with 0 model calls
- [ ] Backend `/health` and `/openapi.json` respond
- [ ] One complete live Nemotron analysis ("Analyze my week"); the attribution names Nemotron, not
      the rule-based fallback
- [ ] Build a weekly plan and approve it
- [ ] Add the unexpected meeting, review the conflict and repair options, and approve one
- [ ] Planning memory: save it after approval, see it on `/setup`, then delete it
- [ ] Phone notification on Android Chrome: grant permission, tap the send button, and see it in
      the notification tray
- [ ] Tapping the notification opens or focuses `/setup`

## 5. If something goes wrong

- **Browser shows a CORS error:** `CORS_ALLOWED_ORIGINS` does not exactly match the page's origin
  (scheme and host, no path). Fix it in Render and restart.
- **Calls go to the wrong place or to `localhost`:** `NEXT_PUBLIC_API_BASE_URL` was missing or
  changed after the build. Set it for Production and redeploy the frontend.
- **Analysis always says rule-based:** the key is missing, wrong, or Nebius is unreachable. Check
  the Render logs and the key. The rest of the app keeps working.
- **Bad deploy:** in Render or Vercel, redeploy the previous healthy commit from the deploy
  history.
- **Key exposed anywhere:** revoke it in Nebius Token Factory immediately, create a new key, and
  update `NEBIUS_API_KEY` in Render. Never copy a Render secret into a Vercel or `NEXT_PUBLIC_*`
  variable; anything there is public.
