import { describe, expect, it } from "vitest";
import { validateServerEnv } from "@/server/config/env";

const validEnv = {
  NODE_ENV: "test",
  MONGODB_URI: "mongodb://localhost:27017/sard-test",
  AUTH_SECRET: "a-secure-test-secret-with-32-characters",
  AI_VIDEO_PROVIDER: "video-test",
  AI_AUDIO_PROVIDER: "audio-test",
  AI_VIDEO_API_KEY: "video-key",
  AI_AUDIO_API_KEY: "audio-key",
};

describe("server environment validation", () => {
  it("accepts a complete server configuration", () => {
    expect(validateServerEnv(validEnv).MONGODB_URI).toBe(validEnv.MONGODB_URI);
  });

  it("rejects missing secrets and public-style MongoDB values", () => {
    expect(() => validateServerEnv({ ...validEnv, AUTH_SECRET: undefined })).toThrow();
    expect(() => validateServerEnv({ ...validEnv, MONGODB_URI: "https://example.com" })).toThrow();
  });
});
