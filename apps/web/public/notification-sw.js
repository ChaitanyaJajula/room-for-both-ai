// Room for Both notification worker. Its only job is to show one fixed-title, non-sensitive
// notification when the page asks, and to bring the app forward when it is tapped.
// It makes no network requests, caches nothing and stores nothing.
"use strict";

const TITLE = "Room for Both";
const TAG = "room-for-both-plan";
const MESSAGE_TYPE = "room-for-both:show-plan-notification";
const MAX_BODY_LENGTH = 140;
const APP_PATH = "/setup";

// The page sends { type, body } and nothing else. Anything different is ignored.
function validBody(data) {
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const keys = Object.keys(data);
  if (keys.length !== 2 || !keys.includes("type") || !keys.includes("body")) return null;
  if (data.type !== MESSAGE_TYPE || typeof data.body !== "string") return null;
  const body = data.body.trim();
  if (body.length === 0 || body.length > MAX_BODY_LENGTH) return null;
  if (/[\u0000-\u001f\u007f]/.test(body)) return null;
  return body;
}

// Notification data is only ever the app's own setup URL, whatever a notification carries.
function targetUrl(data) {
  const fallback = new URL(APP_PATH, self.location.origin).href;
  try {
    const url = new URL(data && data.url, self.location.origin);
    return url.origin === self.location.origin && url.pathname === APP_PATH ? url.href : fallback;
  } catch {
    return fallback;
  }
}

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  // The page gives us a port so it can learn whether the browser accepted the notification.
  const port = event.ports && event.ports[0];
  const reply = (ok) => {
    try {
      if (port) port.postMessage({ ok });
    } catch {
      // The page stopped listening; nothing to do.
    }
  };

  const body = validBody(event.data);
  if (body === null) {
    reply(false);
    return;
  }

  event.waitUntil(
    self.registration
      .showNotification(TITLE, {
        body,
        tag: TAG,
        renotify: true,
        data: { url: new URL(APP_PATH, self.location.origin).href },
      })
      .then(
        () => reply(true),
        () => reply(false),
      ),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = targetUrl(event.notification.data);

  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const existing = windows.find((client) => {
        try {
          return new URL(client.url).origin === self.location.origin;
        } catch {
          return false;
        }
      });
      if (existing && typeof existing.focus === "function") return existing.focus();
      return self.clients.openWindow(target);
    })(),
  );
});
