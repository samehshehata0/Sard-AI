import { describe, expect, it } from "vitest";
import { failurePayload, successPayload } from "@/server/responses/api-response";

describe("API response helpers", () => {
  it("creates the standard success envelope", () => {
    expect(successPayload({ id: "1" }, "تم")).toEqual({ success: true, data: { id: "1" }, message: "تم" });
  });

  it("creates the standard failure envelope", () => {
    expect(failurePayload("VALIDATION_ERROR", "غير صالح", { field: "email" })).toEqual({
      success: false,
      error: { code: "VALIDATION_ERROR", message: "غير صالح", details: { field: "email" } },
    });
  });
});
