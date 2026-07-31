import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/server/database/connection", () => ({
  getDatabaseStatus: vi.fn(),
}));

import { getDatabaseStatus } from "@/server/database/connection";
import { GET } from "@/app/api/health/route";

const mockedDatabaseStatus = vi.mocked(getDatabaseStatus);

describe("GET /api/health", () => {
  beforeEach(() => mockedDatabaseStatus.mockReset());

  it("returns a healthy response without secrets", async () => {
    mockedDatabaseStatus.mockResolvedValue("connected");
    const response = await GET();
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.success).toBe(true);
    expect(body.data.database).toBe("connected");
    expect(JSON.stringify(body)).not.toContain("API_KEY");
  });

  it("returns 503 when the database is disconnected", async () => {
    mockedDatabaseStatus.mockResolvedValue("disconnected");
    const response = await GET();
    expect(response.status).toBe(503);
  });
});
