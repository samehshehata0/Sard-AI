import "server-only";

import { z } from "zod";

const serverEnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  MONGODB_URI: z.string().min(1, "MONGODB_URI is required").refine(
    (value) => value.startsWith("mongodb://") || value.startsWith("mongodb+srv://"),
    "MONGODB_URI must be a MongoDB connection string",
  ),
  AUTH_SECRET: z.string().min(32, "AUTH_SECRET must contain at least 32 characters"),
  AI_VIDEO_PROVIDER: z.string().trim().min(1, "AI_VIDEO_PROVIDER is required"),
  AI_AUDIO_PROVIDER: z.string().trim().min(1, "AI_AUDIO_PROVIDER is required"),
  AI_VIDEO_API_KEY: z.string().trim().min(1, "AI_VIDEO_API_KEY is required"),
  AI_AUDIO_API_KEY: z.string().trim().min(1, "AI_AUDIO_API_KEY is required"),
});

const authEnvSchema = serverEnvSchema.pick({
  NODE_ENV: true,
  MONGODB_URI: true,
  AUTH_SECRET: true,
});

export type ServerEnv = z.infer<typeof serverEnvSchema>;
export type AuthEnv = z.infer<typeof authEnvSchema>;

export function validateServerEnv(input: Record<string, string | undefined>): ServerEnv {
  return serverEnvSchema.parse(input);
}

export function validateAuthEnv(input: Record<string, string | undefined>): AuthEnv {
  return authEnvSchema.parse(input);
}

let cachedEnv: ServerEnv | undefined;
let cachedAuthEnv: AuthEnv | undefined;

export function getServerEnv(): ServerEnv {
  cachedEnv ??= validateServerEnv(process.env);
  return cachedEnv;
}

export function getAuthEnv(): AuthEnv {
  cachedAuthEnv ??= validateAuthEnv(process.env);
  return cachedAuthEnv;
}
