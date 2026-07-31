import "server-only";

import { model, models, Schema, Types, type HydratedDocument, type Model } from "mongoose";

export interface GenerationJobDocument {
  projectId: Types.ObjectId;
  userId: Types.ObjectId;
  type: "video" | "audio";
  provider: string;
  providerJobId?: string;
  requestPayload: Record<string, unknown>;
  status: "queued" | "processing" | "completed" | "failed" | "cancelled";
  outputUrl?: string;
  errorMessage?: string;
  retryCount: number;
  createdAt: Date;
  updatedAt: Date;
  completedAt?: Date;
}

const generationJobSchema = new Schema<GenerationJobDocument>(
  {
    projectId: { type: Schema.Types.ObjectId, ref: "Project", required: true },
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true },
    type: { type: String, enum: ["video", "audio"], required: true },
    provider: { type: String, required: true, trim: true, maxlength: 100 },
    providerJobId: { type: String, trim: true, maxlength: 500 },
    requestPayload: { type: Schema.Types.Mixed, required: true, default: {} },
    status: { type: String, enum: ["queued", "processing", "completed", "failed", "cancelled"], default: "queued", required: true },
    outputUrl: { type: String, trim: true, maxlength: 2_048 },
    errorMessage: { type: String, trim: true, maxlength: 2_000 },
    retryCount: { type: Number, required: true, default: 0, min: 0, max: 10 },
    completedAt: { type: Date },
  },
  { timestamps: true },
);

generationJobSchema.index({ projectId: 1, status: 1 }, { name: "generation_jobs_project_status" });
generationJobSchema.index({ userId: 1, createdAt: -1 }, { name: "generation_jobs_user_created_at" });

export type GenerationJobHydratedDocument = HydratedDocument<GenerationJobDocument>;
export const GenerationJobModel = (models.GenerationJob as Model<GenerationJobDocument> | undefined) ?? model<GenerationJobDocument>("GenerationJob", generationJobSchema);
