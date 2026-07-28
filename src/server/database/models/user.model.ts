import "server-only";

import { model, models, Schema, type HydratedDocument, type Model } from "mongoose";

export type UserRole = "student_teacher" | "faculty_member" | "supervisor" | "admin";

export interface UserDocument {
  fullName: string;
  email: string;
  passwordHash: string;
  role: UserRole;
  institution?: string;
  avatarUrl?: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

const userSchema = new Schema<UserDocument>(
  {
    fullName: { type: String, required: true, trim: true, minlength: 2, maxlength: 100 },
    email: { type: String, required: true, trim: true, lowercase: true, maxlength: 254 },
    passwordHash: { type: String, required: true, select: false },
    role: { type: String, enum: ["student_teacher", "faculty_member", "supervisor", "admin"], required: true },
    institution: { type: String, trim: true, maxlength: 150 },
    avatarUrl: { type: String, trim: true, maxlength: 2_048 },
    isActive: { type: Boolean, default: true, required: true },
  },
  {
    timestamps: true,
    toJSON: {
      transform: (_document, returned) => {
        delete (returned as unknown as Record<string, unknown>).passwordHash;
        return returned;
      },
    },
  },
);

userSchema.index({ email: 1 }, { unique: true, name: "users_email_unique" });

export type UserHydratedDocument = HydratedDocument<UserDocument>;
export const UserModel = (models.User as Model<UserDocument> | undefined) ?? model<UserDocument>("User", userSchema);
