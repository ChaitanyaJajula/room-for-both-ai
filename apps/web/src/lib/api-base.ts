// Public, non-secret configuration only. Never put credentials in NEXT_PUBLIC_* variables.
export const DEFAULT_API_BASE_URL = "http://localhost:8000";

/**
 * The backend base URL without trailing slashes, so "${base}/api/v1/..." never gets a double
 * slash. A missing or blank value falls back to the local development server.
 */
export function resolveApiBaseUrl(raw: string | undefined): string {
  const value = (raw ?? "").trim().replace(/\/+$/, "");
  return value || DEFAULT_API_BASE_URL;
}
