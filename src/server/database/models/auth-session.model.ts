import "server-only";

import { model, models, Schema, Types, type Model } from "mongoose";

export interface AuthSessionDocument {
  userId: Types.ObjectId;
  tokenHash: string;
  expiresAt: Date;
  createdAt: Date;
  updatedAt: Date;
}

const authSessionSchema = new Schema<AuthSessionDocument>(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true },
    tokenHash: { type: String, required: true },
    expiresAt: { type: Date, required: true },
  },
  { timestamps: true },
);

authSessionSchema.index({ tokenHash: 1 }, { unique: true, name: "auth_sessions_token_unique" });
authSessionSchema.index({ expiresAt: 1 }, { expireAfterSeconds: 0, name: "auth_sessions_expiry_ttl" });
authSessionSchema.index({ userId: 1 }, { name: "auth_sessions_user" });

export const AuthSessionModel =
  (models.AuthSession as Model<AuthSessionDocument> | undefined) ??
  model<AuthSessionDocument>("AuthSession", authSessionSchema);
