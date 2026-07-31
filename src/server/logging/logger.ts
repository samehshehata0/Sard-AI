import "server-only";

type LogContext = Record<string, unknown>;

const redactedKeys = /password|passwordHash|token|authorization|cookie|secret|api.?key|prompt/i;

function sanitize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, redactedKeys.test(key) ? "[REDACTED]" : sanitize(item)]),
    );
  }
  return value;
}

function write(level: "info" | "warn" | "error", message: string, context?: LogContext) {
  const entry = { level, message, timestamp: new Date().toISOString(), ...(context ? { context: sanitize(context) } : {}) };
  const serialized = JSON.stringify(entry);
  if (level === "error") console.error(serialized);
  else if (level === "warn") console.warn(serialized);
  else console.info(serialized);
}

export const logger = {
  info: (message: string, context?: LogContext) => write("info", message, context),
  warn: (message: string, context?: LogContext) => write("warn", message, context),
  error: (message: string, context?: LogContext) => write("error", message, context),
};
