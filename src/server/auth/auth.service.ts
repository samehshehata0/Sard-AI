import "server-only";

import { compare, hash } from "bcryptjs";
import { connectToDatabase } from "@/server/database/connection";
import { UserModel } from "@/server/database/models/user.model";
import { AppError } from "@/server/errors/app-error";
import { createSession } from "@/server/auth/session";
import { toAuthUserDto } from "@/server/auth/user-dto";
import type { LoginInput, RegisterInput, UpdateProfileInput } from "@/server/auth/auth.schemas";

const PASSWORD_HASH_ROUNDS = 12;
const INVALID_CREDENTIALS_MESSAGE = "البريد الإلكتروني أو كلمة المرور غير صحيحة.";
const DUMMY_PASSWORD_HASH = "$2b$12$JmWl9q/08rfezqdHPyzR0uPLOlJqdAsG5IC7qWAafOdAyuRbSJLGe";

export async function registerUser(input: RegisterInput) {
  await connectToDatabase();
  const existing = await UserModel.exists({ email: input.email });
  if (existing) throw AppError.conflict("يوجد حساب مسجل بهذا البريد الإلكتروني.");

  try {
    const user = await UserModel.create({
      fullName: input.fullName,
      email: input.email,
      passwordHash: await hash(input.password, PASSWORD_HASH_ROUNDS),
      role: input.role,
      isActive: true,
    });
    await createSession(String(user._id));
    return toAuthUserDto(user);
  } catch (error) {
    if (isDuplicateKeyError(error)) throw AppError.conflict("يوجد حساب مسجل بهذا البريد الإلكتروني.");
    throw error;
  }
}

export async function loginUser(input: LoginInput) {
  await connectToDatabase();
  const user = await UserModel.findOne({ email: input.email }).select("+passwordHash");
  const passwordMatches = await compare(input.password, user?.passwordHash ?? DUMMY_PASSWORD_HASH);
  if (!user || !user.isActive || !passwordMatches) {
    throw AppError.authentication(INVALID_CREDENTIALS_MESSAGE);
  }
  await createSession(String(user._id), input.rememberMe);
  return toAuthUserDto(user);
}

export async function updateUserProfile(userId: string, input: UpdateProfileInput) {
  await connectToDatabase();
  const fieldsToSet = {
    ...(input.fullName !== undefined ? { fullName: input.fullName } : {}),
    ...(input.institution !== undefined && input.institution !== null ? { institution: input.institution } : {}),
    ...(input.avatarUrl !== undefined && input.avatarUrl !== null ? { avatarUrl: input.avatarUrl } : {}),
  };
  const fieldsToUnset = {
    ...(input.institution === null ? { institution: 1 } : {}),
    ...(input.avatarUrl === null ? { avatarUrl: 1 } : {}),
  };
  const update = {
    ...(Object.keys(fieldsToSet).length ? { $set: fieldsToSet } : {}),
    ...(Object.keys(fieldsToUnset).length ? { $unset: fieldsToUnset } : {}),
  };
  const user = await UserModel.findOneAndUpdate({ _id: userId, isActive: true }, update, {
    new: true,
    runValidators: true,
  });
  if (!user) throw AppError.notFound("تعذر العثور على المستخدم.");
  return toAuthUserDto(user);
}

function isDuplicateKeyError(error: unknown): error is { code: number } {
  return typeof error === "object" && error !== null && "code" in error && error.code === 11000;
}
