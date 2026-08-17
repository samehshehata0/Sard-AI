import 'server-only';

import { createHmac, randomBytes } from 'node:crypto';
import { cookies } from 'next/headers';
import { connectToDatabase } from '@/server/database/connection';
import { AuthSessionModel } from '@/server/database/models/auth-session.model';
import { UserModel, type UserRole } from '@/server/database/models/user.model';
import { getAuthEnv } from '@/server/config/env';
import { AppError } from '@/server/errors/app-error';
import { toAuthUserDto, type AuthUserDto } from '@/server/auth/user-dto';
import { SESSION_COOKIE_NAME } from '@/lib/auth/constants';
import { assertRole } from '@/server/auth/authorization';

export const DEFAULT_SESSION_DURATION_SECONDS = 24 * 60 * 60;
export const REMEMBER_ME_SESSION_DURATION_SECONDS = 400 * 24 * 60 * 60;

function hashSessionToken(token: string): string {
  return createHmac('sha256', getAuthEnv().AUTH_SECRET)
    .update(token)
    .digest('hex');
}

function cookieOptions(expires?: Date) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: getAuthEnv().NODE_ENV === 'production',
    path: '/',
    ...(expires ? { expires } : {}),
  };
}

export async function createSession(
  userId: string,
  rememberMe = false,
): Promise<void> {
  await connectToDatabase();
  const cookieStore = await cookies();
  const existingToken = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  if (existingToken)
    await AuthSessionModel.deleteOne({
      tokenHash: hashSessionToken(existingToken),
    });

  const durationSeconds = rememberMe
    ? REMEMBER_ME_SESSION_DURATION_SECONDS
    : DEFAULT_SESSION_DURATION_SECONDS;
  const token = randomBytes(32).toString('base64url');
  const expiresAt = new Date(Date.now() + durationSeconds * 1_000);
  await AuthSessionModel.create({
    userId,
    tokenHash: hashSessionToken(token),
    expiresAt,
  });
  cookieStore.set(SESSION_COOKIE_NAME, token, cookieOptions(expiresAt));
}

export async function getCurrentUser(): Promise<AuthUserDto | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  if (!token) return null;

  await connectToDatabase();
  const session = await AuthSessionModel.findOne({
    tokenHash: hashSessionToken(token),
    expiresAt: { $gt: new Date() },
  }).lean();
  if (!session) return null;

  const user = await UserModel.findOne({
    _id: session.userId,
    isActive: true,
  }).lean();
  if (!user) return null;
  return toAuthUserDto(user);
}

export async function requireUser(): Promise<AuthUserDto> {
  const user = await getCurrentUser();
  if (!user) throw AppError.authentication();
  return user;
}

export async function requireRole(
  ...allowedRoles: UserRole[]
): Promise<AuthUserDto> {
  const user = await requireUser();
  assertRole(user.role, allowedRoles);
  return user;
}

export async function clearSession(): Promise<void> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE_NAME)?.value;
  cookieStore.set(SESSION_COOKIE_NAME, '', {
    ...cookieOptions(new Date(0)),
    maxAge: 0,
  });
  if (token) {
    await connectToDatabase();
    await AuthSessionModel.deleteOne({ tokenHash: hashSessionToken(token) });
  }
}
