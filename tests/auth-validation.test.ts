import { describe, expect, it } from "vitest";
import { loginSchema, registerSchema } from "@/lib/validations";

describe("authentication form validation", () => {
  it.each(["student_teacher", "faculty_member", "supervisor"] as const)(
    "normalizes a valid %s registration payload",
    (role) => {
      expect(registerSchema.parse({
        fullName: "  سامح أحمد  ",
        email: "  SAMEH@EXAMPLE.COM  ",
        password: "secure123",
        confirmPassword: "secure123",
        role,
      })).toEqual({
        fullName: "سامح أحمد",
        email: "sameh@example.com",
        password: "secure123",
        confirmPassword: "secure123",
        role,
      });
    },
  );

  it("attaches a password mismatch to confirmPassword", () => {
    const result = registerSchema.safeParse({
      fullName: "سامح أحمد",
      email: "sameh@example.com",
      password: "secure123",
      confirmPassword: "different123",
      role: "student_teacher",
    });
    expect(result.success).toBe(false);
    if (!result.success) expect(result.error.issues[0]?.path).toEqual(["confirmPassword"]);
  });

  it("normalizes login email and sends only API fields", () => {
    expect(loginSchema.parse({ email: " SAMEH@EXAMPLE.COM ", password: "secure123" })).toEqual({
      email: "sameh@example.com",
      password: "secure123",
    });
  });
});
