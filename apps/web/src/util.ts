import { ApiError } from './api';

/** Human-readable message for any thrown value (Error, ApiError, string...). */
export function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    return e.message;
  }
  if (e instanceof Error) {
    return e.message;
  }
  return String(e);
}

/** Format an ISO-8601 timestamp for display; tolerant of null/invalid input. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleString();
}

/** Short relative-ish label that always shows something useful. */
export function fmtShort(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
