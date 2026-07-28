import "server-only";

import { AppError } from "@/server/errors/app-error";

export function assertOwnership(ownerId: unknown, authenticatedUserId: string): void {
  if (String(ownerId) !== authenticatedUserId) throw AppError.notFound();
}

export function ownedByUserFilter(userId: string) {
  return { userId };
}
