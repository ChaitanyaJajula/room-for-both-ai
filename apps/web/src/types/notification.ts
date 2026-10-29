// Types for the device ("phone") notification. Mirrors the message public/notification-sw.js accepts.

export const NOTIFICATION_MESSAGE_TYPE = "room-for-both:show-plan-notification";

export type NotificationPermissionState = "default" | "granted" | "denied" | "unsupported";

/** The only message the notification worker accepts. */
export interface PlanNotificationMessage {
  type: typeof NOTIFICATION_MESSAGE_TYPE;
  body: string;
}

export type NotificationFailure = "unsupported" | "denied" | "dismissed" | "failed";

export type NotificationResult = { ok: true } | { ok: false; reason: NotificationFailure };

/** The browser pieces the helper needs, so they can be replaced in tests. */
export interface NotificationEnv {
  permission: () => NotificationPermissionState;
  requestPermission: () => Promise<NotificationPermission>;
  register: (scriptUrl: string) => Promise<unknown>;
  ready: () => Promise<{ active: ServiceWorker | null }>;
}
