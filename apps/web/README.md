# Room for Both AI: web frontend

The Next.js 16 (App Router, React 19, TypeScript) interface for Room for Both AI. It handles setup, plan review and approval, conflict repair, browser-local planning memory, device notifications and the reliability dashboard.

- Project overview: [root README](../../README.md)
- Deployment: [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md)
- Architecture: [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
- Live: https://room-for-both-ai.vercel.app

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Introduction |
| `/setup` | Work hours, focus windows, boundaries, analysis, plan, approval, repair, memory, notification |
| `/evaluation` | Public deterministic reliability dashboard |

## Environment

The frontend reads one public setting:

| Variable | Meaning |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the FastAPI backend. Local default: `http://localhost:8000`. In production, the Render service's HTTPS URL. Trailing slashes are removed. |

It is read at **build time**, so changing it on Vercel needs a redeploy. Use `https` in production or browsers block the calls as mixed content.

**Never put API keys or any secret in a `NEXT_PUBLIC_*` variable.** Anything with that prefix is shipped to every visitor's browser. The Nebius key belongs only to the backend.

## Commands

Run from this folder (`apps/web`) in PowerShell:

```powershell
npm install
Copy-Item .env.example .env.local   # points the app at http://localhost:8000
npm run dev                         # http://localhost:3000
npm run lint
npm run build
npm run start                       # serve the production build
```

The backend must be running (see the root README) for analysis, planning, repair and evaluation to work.

## Browser storage and notifications

- Planning memory is saved to `localStorage` only on an explicit click and can be deleted from the interface. It is never sent to the backend.
- The approved plan is held in `sessionStorage` for the current tab.
- `public/notification-sw.js` is a service worker that displays a notification when the user presses the send button and has granted permission. It is served with no-cache headers (see `next.config.ts`).
