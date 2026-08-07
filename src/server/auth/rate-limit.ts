import "server-only";

import { AppError } from "@/server/errors/app-error";

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

declare global {
  var __sardLoginRateLimits: Map<string, RateLimitEntry> | undefined;
}

const attempts = globalThis.__sardLoginRateLimits ?? new Map<string, RateLimitEntry>();
globalThis.__sardLoginRateLimits = attempts;

const WINDOW_MS = 15 * 60 * 1_000;
const MAX_ATTEMPTS = 5;

function requestIp(request: Request): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || request.headers.get("x-real-ip") || "unknown";
}

export function enforceLoginRateLimit(request: Request, normalizedEmail: string): void {
  const now = Date.now();
  if (attempts.size > 10_000) {
    for (const [storedKey, entry] of attempts) {
      if (entry.resetAt <= now) attempts.delete(storedKey);
    }
  }
  const key = `${requestIp(request)}:${normalizedEmail}`;
  const current = attempts.get(key);
  if (!current || current.resetAt <= now) {
    attempts.set(key, { count: 1, resetAt: now + WINDOW_MS });
    return;
  }
  current.count += 1;
  if (current.count > MAX_ATTEMPTS) throw AppError.rateLimited();
}

export function resetLoginRateLimit(request: Request, normalizedEmail: string): void {
  attempts.delete(`${requestIp(request)}:${normalizedEmail}`);
}
