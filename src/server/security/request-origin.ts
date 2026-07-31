import "server-only";

import { AppError } from "@/server/errors/app-error";

export function assertSameOrigin(request: Request): void {
  const origin = request.headers.get("origin");
  if (!origin) return;

  let requestOrigin: string;
  try {
    requestOrigin = new URL(request.url).origin;
  } catch {
    throw AppError.authorization("مصدر الطلب غير مسموح.");
  }
  if (origin !== requestOrigin) throw AppError.authorization("مصدر الطلب غير مسموح.");
}
