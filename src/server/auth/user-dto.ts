import "server-only";

import type { UserDocument } from "@/server/database/models/user.model";

type UserSource = UserDocument & { _id: unknown };

export interface AuthUserDto {
  id: string;
  fullName: string;
  email: string;
  role: UserDocument["role"];
  institution: string | null;
  avatarUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

export function toAuthUserDto(user: UserSource): AuthUserDto {
  return {
    id: String(user._id),
    fullName: user.fullName,
    email: user.email,
    role: user.role,
    institution: user.institution ?? null,
    avatarUrl: user.avatarUrl ?? null,
    createdAt: user.createdAt.toISOString(),
    updatedAt: user.updatedAt.toISOString(),
  };
}
