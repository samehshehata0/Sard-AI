import "server-only";

import { model, models, Schema, Types, type HydratedDocument, type Model } from "mongoose";

export interface AssessmentDocument {
  projectId: Types.ObjectId;
  userId: Types.ObjectId;
  stressAnswers: number[];
  motivationAnswers: number[];
  stressScore: number;
  motivationScore: number;
  wellBeingScore: number;
  createdAt: Date;
  updatedAt: Date;
}

const answerField = { type: [{ type: Number, min: 1, max: 5 }], required: true };
const scoreField = { type: Number, required: true, min: 0, max: 100 };

const assessmentSchema = new Schema<AssessmentDocument>(
  {
    projectId: { type: Schema.Types.ObjectId, ref: "Project", required: true },
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true },
    stressAnswers: answerField,
    motivationAnswers: answerField,
    stressScore: scoreField,
    motivationScore: scoreField,
    wellBeingScore: scoreField,
  },
  { timestamps: true },
);

assessmentSchema.index({ userId: 1, projectId: 1, createdAt: -1 }, { name: "assessments_user_project_created_at" });

export type AssessmentHydratedDocument = HydratedDocument<AssessmentDocument>;
export const AssessmentModel = (models.Assessment as Model<AssessmentDocument> | undefined) ?? model<AssessmentDocument>("Assessment", assessmentSchema);
