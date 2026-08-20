import "server-only";

import mongoose, { type Mongoose } from "mongoose";
import { getAuthEnv } from "@/server/config/env";
import { AppError } from "@/server/errors/app-error";
import { logger } from "@/server/logging/logger";

interface MongooseCache {
  connection: Mongoose | null;
  promise: Promise<Mongoose> | null;
}

declare global {
  var __sardMongoose: MongooseCache | undefined;
}

const cache = globalThis.__sardMongoose ?? { connection: null, promise: null };
globalThis.__sardMongoose = cache;

export async function connectToDatabase(): Promise<Mongoose> {
  if (cache.connection && mongoose.connection.readyState === 1) return cache.connection;

  if (!cache.promise) {
    const { MONGODB_URI } = getAuthEnv();
    cache.promise = mongoose.connect(MONGODB_URI, {
      bufferCommands: false,
      maxPoolSize: 10,
      minPoolSize: 0,
      serverSelectionTimeoutMS: 5_000,
    });
  }

  try {
    cache.connection = await cache.promise;
    return cache.connection;
  } catch (error) {
    cache.promise = null;
    logger.error("MongoDB connection failed", {
      errorName: error instanceof Error ? error.name : "UnknownError",
      errorMessage: error instanceof Error ? error.message : String(error),
    });
    throw AppError.databaseUnavailable();
  }
}

export async function getDatabaseStatus(): Promise<"connected" | "disconnected"> {
  try {
    await connectToDatabase();
    return mongoose.connection.readyState === 1 ? "connected" : "disconnected";
  } catch {
    return "disconnected";
  }
}
