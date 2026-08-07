import "server-only";

import type { UserRole } from "@/server/database/models/user.model";
import { AppError } from "@/server/errors/app-error";

export function assertRole(currentRole: UserRole, allowedRoles: readonly UserRole[]): void {
  if (!allowedRoles.includes(currentRole)) throw AppError.authorization();
}
