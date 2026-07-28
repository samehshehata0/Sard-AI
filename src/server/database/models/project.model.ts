import "server-only";

import { model, models, Schema, Types, type HydratedDocument, type Model } from "mongoose";

export type ProjectStatus = "draft" | "ready" | "processing" | "completed" | "partially_completed" | "failed";

export interface ProjectDocument {
  userId: Types.ObjectId;
  title: string;
  educationalTopic: string;
  learningObjectives: string[];
  learnerAge: string;
  educationLevel: string;
  learnerCharacteristics: string;
  storyStyle: string;
  voiceTone: string;
  requestedOutputs: ("audio" | "video")[];
  prompt: string;
  status: ProjectStatus;
  videoUrl?: string;
  audioUrl?: string;
  thumbnailUrl?: string;
  errorMessage?: string;
  createdAt: Date;
  updatedAt: Date;
}

const projectSchema = new Schema<ProjectDocument>(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true },
    title: { type: String, required: true, trim: true, minlength: 1, maxlength: 150 },
    educationalTopic: { type: String, required: true, trim: true, maxlength: 500 },
    learningObjectives: {
      type: [{ type: String, trim: true, minlength: 1, maxlength: 500 }],
      required: true,
      validate: { validator: (values: string[]) => values.length >= 1 && values.length <= 20, message: "Learning objectives must contain 1 to 20 items" },
    },
    learnerAge: { type: String, required: true, trim: true, maxlength: 50 },
    educationLevel: { type: String, required: true, trim: true, maxlength: 100 },
    learnerCharacteristics: { type: String, required: true, trim: true, maxlength: 1_000 },
    storyStyle: { type: String, required: true, trim: true, maxlength: 100 },
    voiceTone: { type: String, required: true, trim: true, maxlength: 100 },
    requestedOutputs: {
      type: [{ type: String, enum: ["audio", "video"] }],
      required: true,
      validate: { validator: (values: string[]) => values.length >= 1 && new Set(values).size === values.length, message: "Requested outputs must be non-empty and unique" },
    },
    prompt: { type: String, required: true, trim: true, maxlength: 10_000 },
    status: { type: String, enum: ["draft", "ready", "processing", "completed", "partially_completed", "failed"], default: "draft", required: true },
    videoUrl: { type: String, trim: true, maxlength: 2_048 },
    audioUrl: { type: String, trim: true, maxlength: 2_048 },
    thumbnailUrl: { type: String, trim: true, maxlength: 2_048 },
    errorMessage: { type: String, trim: true, maxlength: 2_000 },
  },
  { timestamps: true },
);

projectSchema.index({ userId: 1, createdAt: -1 }, { name: "projects_user_created_at" });

export type ProjectHydratedDocument = HydratedDocument<ProjectDocument>;
export const ProjectModel = (models.Project as Model<ProjectDocument> | undefined) ?? model<ProjectDocument>("Project", projectSchema);
