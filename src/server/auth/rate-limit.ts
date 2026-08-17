import "server-only";

import { AppError } from "@/server/errors/app-error";

interface RateLimitEntry {
  count: number;
  resetAt: number;
}

declare global {
  var __sardRateLimits: Map<string, RateLimitEntry> | undefined;
}

const attempts = globalThis.__sardRateLimits ?? new Map<string, RateLimitEntry>();
globalThis.__sardRateLimits = attempts;

const LOGIN_WINDOW_MS = 15 * 60 * 1_000;
const LOGIN_MAX_ATTEMPTS = 5;
const REGISTER_WINDOW_MS = 60 * 60 * 1_000;
const REGISTER_MAX_ATTEMPTS = 5;

function requestIp(request: Request): string {
  return request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || request.headers.get("x-real-ip") || "unknown";
}

function enforceRateLimit(bucket: string, key: string, maxAttempts: number, windowMs: number): void {
  const now = Date.now();
  if (attempts.size > 10_000) {
    for (const [storedKey, entry] of attempts) {
      if (entry.resetAt <= now) attempts.delete(storedKey);
    }
  }
  const bucketKey = `${bucket}:${key}`;
  const current = attempts.get(bucketKey);
  if (!current || current.resetAt <= now) {
    attempts.set(bucketKey, { count: 1, resetAt: now + windowMs });
    return;
  }
  current.count += 1;
  if (current.count > maxAttempts) throw AppError.rateLimited(undefined, Math.ceil((current.resetAt - now) / 1_000));
}

export function enforceLoginRateLimit(request: Request, normalizedEmail: string): void {
  enforceRateLimit("login", `${requestIp(request)}:${normalizedEmail}`, LOGIN_MAX_ATTEMPTS, LOGIN_WINDOW_MS);
}

export function resetLoginRateLimit(request: Request, normalizedEmail: string): void {
  attempts.delete(`login:${requestIp(request)}:${normalizedEmail}`);
}

export function enforceRegisterRateLimit(request: Request, normalizedEmail: string): void {
  enforceRateLimit("register", `${requestIp(request)}:${normalizedEmail}`, REGISTER_MAX_ATTEMPTS, REGISTER_WINDOW_MS);
}
