import "server-only";

import { AppError } from "@/server/errors/app-error";

export function assertSameOrigin(request: Request): void {
  const origin = request.headers.get("origin");
  if (!origin) return;

  const host = request.headers.get("host");
  if (!host) throw AppError.authorization("مصدر الطلب غير مسموح.");

  let originHost: string;
  try {
    originHost = new URL(origin).host;
  } catch {
    throw AppError.authorization("مصدر الطلب غير مسموح.");
  }

  if (originHost !== host) throw AppError.authorization("مصدر الطلب غير مسموح.");
}
