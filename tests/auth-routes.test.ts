import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppError } from "@/server/errors/app-error";

vi.mock("@/server/auth/auth.service", () => ({
  registerUser: vi.fn(),
  loginUser: vi.fn(),
  updateUserProfile: vi.fn(),
}));
vi.mock("@/server/auth/session", () => ({
  requireUser: vi.fn(),
  clearSession: vi.fn(),
}));
vi.mock("@/server/auth/rate-limit", () => ({
  enforceLoginRateLimit: vi.fn(),
  resetLoginRateLimit: vi.fn(),
}));

import { registerUser, loginUser } from "@/server/auth/auth.service";
import { clearSession, requireUser } from "@/server/auth/session";
import { POST as register } from "@/app/api/auth/register/route";
import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { GET as me } from "@/app/api/auth/me/route";

const mockedRegisterUser = vi.mocked(registerUser);
const mockedLoginUser = vi.mocked(loginUser);
const mockedRequireUser = vi.mocked(requireUser);
const mockedClearSession = vi.mocked(clearSession);

const user = {
  id: "507f1f77bcf86cd799439011",
  fullName: "سامح أحمد",
  email: "sameh@example.com",
  role: "student_teacher" as const,
  institution: null,
  avatarUrl: null,
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

function jsonRequest(url: string, body: unknown) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json", "x-forwarded-for": "127.0.0.1" },
    body: JSON.stringify(body),
  });
}

describe("authentication route handlers", () => {
  beforeEach(() => vi.clearAllMocks());

  it("registers a valid user", async () => {
    mockedRegisterUser.mockResolvedValue(user);
    const response = await register(jsonRequest("http://localhost/api/auth/register", {
      fullName: "سامح أحمد",
      email: "SAMEH@EXAMPLE.COM",
      password: "secure123",
      confirmPassword: "secure123",
      role: "student_teacher",
    }));
    const body = await response.json();
    expect(response.status).toBe(201);
    expect(body.data.user).toEqual(user);
    expect(mockedRegisterUser).toHaveBeenCalledWith(expect.objectContaining({ email: "sameh@example.com" }));
  });

  it("returns conflict for a duplicate email", async () => {
    mockedRegisterUser.mockRejectedValue(AppError.conflict("يوجد حساب مسجل بهذا البريد الإلكتروني."));
    const response = await register(jsonRequest("http://localhost/api/auth/register", {
      fullName: "سامح أحمد",
      email: "sameh@example.com",
      password: "secure123",
      confirmPassword: "secure123",
      role: "student_teacher",
    }));
    expect(response.status).toBe(409);
    expect((await response.json()).error.code).toBe("CONFLICT");
  });

  it("rejects invalid registration before calling the service", async () => {
    const response = await register(jsonRequest("http://localhost/api/auth/register", {
      fullName: "1",
      email: "invalid",
      password: "short",
      confirmPassword: "different",
      role: "admin",
    }));
    expect(response.status).toBe(400);
    expect((await response.json()).error.details).toMatchObject({
      fullName: expect.any(String),
      email: expect.any(String),
      password: expect.any(String),
      role: "الدور غير صالح.",
    });
    expect(mockedRegisterUser).not.toHaveBeenCalled();
  });

  it("returns field details when registration confirmation is missing", async () => {
    const response = await register(jsonRequest("http://localhost/api/auth/register", {
      fullName: "سامح أحمد",
      email: "sameh@example.com",
      password: "secure123",
      role: "student_teacher",
    }));
    expect(response.status).toBe(400);
    expect((await response.json()).error.details).toEqual({ confirmPassword: expect.any(String) });
    expect(mockedRegisterUser).not.toHaveBeenCalled();
  });

  it("logs in with valid credentials", async () => {
    mockedLoginUser.mockResolvedValue(user);
    const response = await login(jsonRequest("http://localhost/api/auth/login", {
      email: "sameh@example.com",
      password: "secure123",
    }));
    expect(response.status).toBe(200);
    expect((await response.json()).data.user.email).toBe(user.email);
    expect(mockedLoginUser).toHaveBeenCalledWith({ email: "sameh@example.com", password: "secure123" });
  });

  it("rejects UI-only login fields with useful validation details", async () => {
    const response = await login(jsonRequest("http://localhost/api/auth/login", {
      email: "sameh@example.com",
      password: "secure123",
      remember: true,
    }));
    expect(response.status).toBe(400);
    expect((await response.json()).error.details).toEqual({ request: expect.any(String) });
    expect(mockedLoginUser).not.toHaveBeenCalled();
  });

  it("uses a generic error for invalid credentials", async () => {
    mockedLoginUser.mockRejectedValue(AppError.authentication("البريد الإلكتروني أو كلمة المرور غير صحيحة."));
    const response = await login(jsonRequest("http://localhost/api/auth/login", {
      email: "unknown@example.com",
      password: "secure123",
    }));
    const body = await response.json();
    expect(response.status).toBe(401);
    expect(body.error.message).toBe("البريد الإلكتروني أو كلمة المرور غير صحيحة.");
  });

  it("returns the current authenticated user", async () => {
    mockedRequireUser.mockResolvedValue(user);
    const response = await me();
    expect(response.status).toBe(200);
    expect((await response.json()).data.id).toBe(user.id);
  });

  it("rejects unauthenticated current-user requests", async () => {
    mockedRequireUser.mockRejectedValue(AppError.authentication());
    const response = await me();
    expect(response.status).toBe(401);
  });

  it("clears the session on logout", async () => {
    mockedClearSession.mockResolvedValue();
    const response = await logout(new Request("http://localhost/api/auth/logout", { method: "POST" }));
    expect(response.status).toBe(200);
    expect(mockedClearSession).toHaveBeenCalledOnce();
  });
});
