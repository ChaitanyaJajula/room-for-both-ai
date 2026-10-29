"use client";

import { useReducer, useRef, useState, useSyncExternalStore } from "react";

import {
  buildNotificationBody,
  getPermissionState,
  sendPlanNotification,
} from "@/lib/phone-notification";
import type { NotificationFailure } from "@/types/notification";

type Status =
  | { state: "idle" }
  | { state: "working" }
  | { state: "sent" }
  | { state: "failed"; reason: NotificationFailure };

const primaryButton =
  "min-h-10 rounded-full bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white shadow-soft hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70";
const secondaryButton =
  "min-h-10 rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

const BLOCKED = "Notifications are blocked. Enable them in your browser or phone settings to try again.";
const FAILED =
  "The notification could not be sent. Check this browser’s notification settings and try again.";
const DISMISSED =
  "Notification permission was not granted, so nothing was sent. You can try again.";

// Follows the browser's own permission setting when it can report changes.
function subscribe(onChange: () => void): () => void {
  let status: PermissionStatus | null = null;
  let active = true;
  try {
    navigator.permissions
      ?.query({ name: "notifications" })
      .then((result) => {
        if (!active) return;
        status = result;
        result.addEventListener("change", onChange);
      })
      .catch(() => undefined);
  } catch {
    // The Permissions API is optional; the manual re-check button covers it.
  }
  return () => {
    active = false;
    status?.removeEventListener("change", onChange);
  };
}

/**
 * Sends one device notification about the approved plan, only when the user clicks. Render it
 * keyed by the approval time so a newly approved plan starts with a fresh state.
 */
export function PhoneNotificationCard({
  workMinutes,
  personalMinutes,
}: {
  workMinutes: number;
  personalMinutes: number;
}) {
  const permission = useSyncExternalStore(subscribe, () => getPermissionState(), () => "unsupported");
  const [status, setStatus] = useState<Status>({ state: "idle" });
  const [, recheck] = useReducer((n: number) => n + 1, 0);
  // State updates are asynchronous, so a rapid second click needs its own guard.
  const inFlight = useRef(false);
  const working = status.state === "working";

  // Only aggregate numbers from the approved plan are ever sent.
  if (buildNotificationBody(workMinutes, personalMinutes) === null) return null;

  const send = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setStatus({ state: "working" });
    try {
      const result = await sendPlanNotification(workMinutes, personalMinutes);
      setStatus(result.ok ? { state: "sent" } : { state: "failed", reason: result.reason });
      recheck();
    } finally {
      inFlight.current = false;
    }
  };

  const failureText =
    status.state === "failed" && status.reason === "dismissed"
      ? DISMISSED
      : status.state === "failed" && status.reason === "unsupported"
        ? "Notifications are not supported in this browser."
        : status.state === "failed" && status.reason !== "denied"
          ? FAILED
          : null;

  return (
    <section
      aria-labelledby="phone-notification-title"
      className="space-y-3 rounded-2xl border border-line bg-surface p-4 shadow-soft"
    >
      <h3 id="phone-notification-title" className="font-serif text-lg font-semibold">
        Phone notification
      </h3>
      <p className="text-sm">
        Send a private test notification to this device. On a phone, it appears in the
        notification tray.
      </p>

      {permission === "unsupported" ? (
        <p className="text-sm font-medium">Notifications are not supported in this browser.</p>
      ) : permission === "denied" ? (
        <div className="space-y-3">
          <p className="text-sm font-medium text-terracotta-dark">{BLOCKED}</p>
          <button type="button" onClick={recheck} className={secondaryButton}>
            Check permission again
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={send}
          disabled={working}
          aria-busy={working}
          className={primaryButton}
        >
          {working
            ? "Sending notification…"
            : permission === "granted"
              ? "Send phone notification"
              : "Enable and send notification"}
        </button>
      )}

      <div role="status" aria-live="polite" className="space-y-1">
        {working ? <p className="text-sm font-medium text-teal-800">Sending notification…</p> : null}
        {status.state === "sent" ? (
          <p className="text-sm font-semibold text-teal-800">
            <span aria-hidden="true">✓ </span>Notification sent to this device.
          </p>
        ) : null}
        {failureText && permission !== "denied" && permission !== "unsupported" ? (
          <p className="text-sm font-medium text-terracotta-dark">{failureText}</p>
        ) : null}
      </div>

      <p className="text-xs text-muted">
        Notification permission stays under your browser’s control. Room for Both does not store a
        phone number or send notification data to its backend.
      </p>
    </section>
  );
}
