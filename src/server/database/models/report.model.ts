import "server-only";

import { model, models, Schema, Types, type HydratedDocument, type Model } from "mongoose";

export interface ReportDocument {
  projectId: Types.ObjectId;
  userId: Types.ObjectId;
  progressScore: number;
  wellBeingScore: number;
  recommendations: string[];
  createdAt: Date;
  updatedAt: Date;
}

const reportSchema = new Schema<ReportDocument>(
  {
    projectId: { type: Schema.Types.ObjectId, ref: "Project", required: true },
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true },
    progressScore: { type: Number, required: true, min: 0, max: 100 },
    wellBeingScore: { type: Number, required: true, min: 0, max: 100 },
    recommendations: {
      type: [{ type: String, trim: true, minlength: 1, maxlength: 1_000 }],
      required: true,
      validate: { validator: (values: string[]) => values.length <= 50, message: "Recommendations cannot exceed 50 items" },
    },
  },
  { timestamps: true },
);

reportSchema.index({ projectId: 1 }, { unique: true, name: "reports_project_unique" });
reportSchema.index({ userId: 1, createdAt: -1 }, { name: "reports_user_created_at" });

export type ReportHydratedDocument = HydratedDocument<ReportDocument>;
export const ReportModel = (models.Report as Model<ReportDocument> | undefined) ?? model<ReportDocument>("Report", reportSchema);
