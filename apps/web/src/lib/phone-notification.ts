// Device ("phone") notification helper. Everything here is browser-only and runs after an
// explicit click: permission is never requested on load, nothing is stored, and no request is
// made to the backend or a model. The notification itself is shown by public/notification-sw.js.
import {
  NOTIFICATION_MESSAGE_TYPE,
  type NotificationEnv,
  type NotificationPermissionState,
  type NotificationResult,
  type PlanNotificationMessage,
} from "@/types/notification";

export const WORKER_URL = "/notification-sw.js";
export const MAX_BODY_LENGTH = 140;
const WORKER_TIMEOUT_MS = 10_000;

const isMinutes = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && Number.isInteger(v) && v >= 0;

/** Aggregate plan numbers only: no titles, boundary names or model output. */
export function buildNotificationBody(workMinutes: number, personalMinutes: number): string | null {
  if (!isMinutes(workMinutes) || !isMinutes(personalMinutes)) return null;
  const body =
    `Your weekly plan is approved: ${workMinutes.toLocaleString("en-US")} work minutes ` +
    `and ${personalMinutes.toLocaleString("en-US")} personal minutes protected.`;
  return body.length <= MAX_BODY_LENGTH ? body : null;
}

/** The same check the worker applies before it shows anything. */
export function isNotificationMessage(value: unknown): value is PlanNotificationMessage {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length !== 2 || !keys.includes("type") || !keys.includes("body")) return false;
  if (record.type !== NOTIFICATION_MESSAGE_TYPE || typeof record.body !== "string") return false;
  const body = record.body.trim();
  return body.length > 0 && body.length <= MAX_BODY_LENGTH && !/[\u0000-\u001f\u007f]/.test(body);
}

/** The real browser APIs, or null on the server and in browsers without them. */
export function browserEnv(): NotificationEnv | null {
  if (typeof window === "undefined" || !("Notification" in window)) return null;
  if (!("serviceWorker" in navigator)) return null;
  return {
    permission: () => Notification.permission as NotificationPermissionState,
    requestPermission: () => Notification.requestPermission(),
    register: (url) => navigator.serviceWorker.register(url),
    ready: () => navigator.serviceWorker.ready,
  };
}

export function getPermissionState(env: NotificationEnv | null = browserEnv()): NotificationPermissionState {
  if (env === null) return "unsupported";
  try {
    return env.permission();
  } catch {
    return "unsupported";
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/** Posts the message and resolves true only when the worker reports the browser accepted it. */
function showThroughWorker(worker: ServiceWorker, message: PlanNotificationMessage): Promise<boolean> {
  const channel = new MessageChannel();
  return withTimeout(
    new Promise<boolean>((resolve) => {
      channel.port1.onmessage = (event: MessageEvent) => {
        resolve(typeof event.data === "object" && event.data !== null && event.data.ok === true);
      };
      worker.postMessage(message, [channel.port2]);
    }),
    WORKER_TIMEOUT_MS,
  ).finally(() => channel.port1.close());
}

/**
 * Sends one notification. Call it directly from a click handler: when permission is still
 * undecided, the browser prompt is the first thing it does, while the click still counts.
 */
export async function sendPlanNotification(
  workMinutes: number,
  personalMinutes: number,
  env: NotificationEnv | null = browserEnv(),
): Promise<NotificationResult> {
  const body = buildNotificationBody(workMinutes, personalMinutes);
  if (body === null) return { ok: false, reason: "failed" };
  if (env === null) return { ok: false, reason: "unsupported" };

  try {
    let permission = env.permission();
    if (permission === "unsupported") return { ok: false, reason: "unsupported" };
    if (permission === "denied") return { ok: false, reason: "denied" };
    if (permission === "default") {
      const answer = await env.requestPermission();
      if (answer === "denied") return { ok: false, reason: "denied" };
      if (answer !== "granted") return { ok: false, reason: "dismissed" };
      permission = "granted";
    }

    await env.register(WORKER_URL);
    const registration = await withTimeout(env.ready(), WORKER_TIMEOUT_MS);
    const worker = registration.active;
    if (!worker) return { ok: false, reason: "failed" };

    const message: PlanNotificationMessage = { type: NOTIFICATION_MESSAGE_TYPE, body };
    const shown = await showThroughWorker(worker, message);
    return shown ? { ok: true } : { ok: false, reason: "failed" };
  } catch {
    // Browser exceptions and internal details are deliberately not passed on.
    return { ok: false, reason: "failed" };
  }
}
