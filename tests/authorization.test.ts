import { describe, expect, it } from "vitest";
import { assertRole } from "@/server/auth/authorization";
import { assertOwnership } from "@/server/security/ownership";

describe("authorization helpers", () => {
  it("allows configured roles and matching ownership", () => {
    expect(() => assertRole("admin", ["admin"])).not.toThrow();
    expect(() => assertOwnership("user-1", "user-1")).not.toThrow();
  });

  it("rejects unauthorized roles and non-owners", () => {
    expect(() => assertRole("student_teacher", ["admin"])).toThrowError(/صلاحية/);
    expect(() => assertOwnership("user-2", "user-1")).toThrowError(/غير موجود/);
  });
});
